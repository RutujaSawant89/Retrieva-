"""Dense (pgvector) and sparse (BM25) retrievers.

Both return ranked ``(chunk_id, score)`` lists restricted to the documents the caller may see.
Permission filtering happens *before* results are returned, never after generation.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass

import numpy as np
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk, DocumentStatus
from app.services.access import document_visibility_for
from app.services.retrieval.bm25 import BM25Index
from app.services.retrieval.types import RetrievalScope, VectorMetric

logger = logging.getLogger(__name__)

# Below this many chunks per organization dense search is exact (sequential scan): HNSW
# post-filtering in a shared multi-tenant index can return too few rows for small tenants.
EXACT_SEARCH_THRESHOLD = 20_000
HNSW_EF_SEARCH = 200


def allowed_document_ids(db: Session, scope: RetrievalScope) -> list[uuid.UUID]:
    stmt = select(Document.id).where(
        document_visibility_for(scope.org_id, scope.user_id, scope.can_manage),
        Document.status == DocumentStatus.COMPLETED,
    )
    if scope.document_ids is not None:
        stmt = stmt.where(Document.id.in_(scope.document_ids))
    return list(db.scalars(stmt))


# --------------------------------------------------------------------------------------
# Dense retrieval (pgvector)
# --------------------------------------------------------------------------------------


def dense_search(
    db: Session,
    scope: RetrievalScope,
    allowed_docs: list[uuid.UUID],
    query_vector: np.ndarray,
    model_version: str,
    top_k: int,
    metric: VectorMetric = "cosine",
    org_chunk_count: int | None = None,
) -> list[tuple[uuid.UUID, float]]:
    if not allowed_docs:
        return []
    vector = query_vector.tolist()
    if metric == "cosine":
        distance = DocumentChunk.embedding.cosine_distance(vector)
        score = 1 - distance
    else:
        distance = DocumentChunk.embedding.max_inner_product(vector)  # negative inner product
        score = -distance
    exact = scope.document_ids is not None or (org_chunk_count or 0) <= EXACT_SEARCH_THRESHOLD
    # "+ 0" makes the ORDER BY expression non-indexable, forcing an exact scan.
    order = distance + 0 if exact else distance
    if not exact:
        db.execute(text(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}"))
    stmt = (
        select(DocumentChunk.id, score.label("score"))
        .where(
            DocumentChunk.organization_id == scope.org_id,
            DocumentChunk.embedding_model == model_version,
            DocumentChunk.document_id.in_(allowed_docs),
        )
        .order_by(order)
        .limit(top_k)
    )
    rows = db.execute(stmt).all()
    if not exact and len(rows) < top_k:
        # Approximate search lost results to filtering; fall back to an exact scan.
        rows = db.execute(stmt.order_by(None).order_by(distance + 0)).all()
    return [(row[0], float(row[1])) for row in rows]


# --------------------------------------------------------------------------------------
# Sparse retrieval (BM25)
# --------------------------------------------------------------------------------------


@dataclass
class _OrgIndex:
    version: tuple[int, str]
    index: BM25Index
    chunk_docs: np.ndarray  # document index per chunk
    doc_index: dict[uuid.UUID, int]


class SparseIndexCache:
    """Per-organization BM25 indexes, rebuilt when the organization's chunk set changes."""

    def __init__(self) -> None:
        self._indexes: dict[uuid.UUID, _OrgIndex] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _version(db: Session, org_id: uuid.UUID) -> tuple[int, str]:
        count, latest = db.execute(
            select(func.count(DocumentChunk.id), func.max(DocumentChunk.created_at)).where(
                DocumentChunk.organization_id == org_id
            )
        ).one()
        return int(count), str(latest)

    def get(self, db: Session, org_id: uuid.UUID) -> _OrgIndex:
        version = self._version(db, org_id)
        cached = self._indexes.get(org_id)
        if cached is not None and cached.version == version:
            return cached
        with self._lock:
            cached = self._indexes.get(org_id)
            if cached is not None and cached.version == version:
                return cached
            rows = db.execute(
                select(
                    DocumentChunk.id,
                    DocumentChunk.document_id,
                    DocumentChunk.content,
                    DocumentChunk.chunk_metadata["context_header"].astext,
                ).where(DocumentChunk.organization_id == org_id)
            ).all()
            doc_index: dict[uuid.UUID, int] = {}
            chunk_docs = np.zeros(len(rows), dtype=np.int32)
            for i, row in enumerate(rows):
                chunk_docs[i] = doc_index.setdefault(row[1], len(doc_index))
            index = BM25Index([r[0] for r in rows], [f"{r[3] or ''}\n{r[2]}" for r in rows])
            built = _OrgIndex(version=version, index=index, chunk_docs=chunk_docs, doc_index=doc_index)
            self._indexes[org_id] = built
            logger.info("bm25_index_built", extra={"org_id": str(org_id), "chunks": len(rows)})
            return built

    def chunk_count(self, db: Session, org_id: uuid.UUID) -> int:
        return self._version(db, org_id)[0]


sparse_cache = SparseIndexCache()


def allowed_mask(org_index: _OrgIndex, allowed_docs: list[uuid.UUID]) -> np.ndarray:
    wanted = [org_index.doc_index[d] for d in allowed_docs if d in org_index.doc_index]
    return np.isin(org_index.chunk_docs, np.asarray(wanted, dtype=np.int32))


def sparse_search(
    org_index: _OrgIndex,
    allowed_docs: list[uuid.UUID],
    query: str | dict[str, float],
    top_k: int,
) -> list[tuple[uuid.UUID, float]]:
    if not allowed_docs:
        return []
    return [
        (chunk_id, score)  # type: ignore[misc]
        for chunk_id, score in org_index.index.search(
            query, top_k, allowed=allowed_mask(org_index, allowed_docs)
        )
    ]
