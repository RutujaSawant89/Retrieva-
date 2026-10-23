"""Retrieval pipeline.

    query ─► plan (normalise, follow-up rewrite, multi-query)
          ─► per query: dense (pgvector) and/or sparse (BM25 [+ PRF expansion])
          ─► Reciprocal Rank Fusion (+ metadata boost)
          ─► near-duplicate removal
          ─► cross-encoder reranking
          ─► relevance threshold, top-k
          ─► optional contextual compression

Every stage can be toggled through ``RetrievalConfig`` so it can be benchmarked in isolation.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.metrics import RETRIEVAL_LATENCY
from app.db.models import Document, DocumentChunk, SearchQuery
from app.services.embeddings.service import EmbeddingService, get_embedding_service
from app.services.reranking.rerankers import Reranker, get_reranker
from app.services.retrieval import query_processing, stores
from app.services.retrieval.analyzer import analyze
from app.services.retrieval.bm25 import BM25Index
from app.services.retrieval.fusion import reciprocal_rank_fusion
from app.services.retrieval.postprocess import compress, remove_near_duplicates
from app.services.retrieval.types import Evidence, RetrievalConfig, RetrievalResult, RetrievalScope

logger = logging.getLogger(__name__)

# "auto" pseudo-relevance feedback runs only when the best BM25 match covers little of the
# query's information (vocabulary mismatch), and only on corpora large enough for feedback
# terms to be meaningful rather than noise.
EXPANSION_WEAK_MATCH = 0.35
EXPANSION_MIN_CORPUS = 100


def lexical_match_strength(index: BM25Index, query: str, top_score: float) -> float:
    """Best BM25 score relative to the score of a passage containing every query term once.

    With tf = 1 and an average-length passage each term contributes exactly its IDF, so
    ``Σ idf(t)`` is a natural, query-length-independent normaliser.
    """
    ideal = sum(index.idf(term) for term in set(analyze(query)))
    return top_score / ideal if ideal > 0 else 0.0


class _Timer:
    def __init__(self) -> None:
        self.timings: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        began = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - began
            self.timings[name] = round(self.timings.get(name, 0.0) + elapsed * 1000, 2)
            RETRIEVAL_LATENCY.labels(name).observe(elapsed)


def _mentioned_documents(db: Session, allowed_docs: list[uuid.UUID], query: str) -> list[uuid.UUID]:
    """Documents whose title is mentioned in the query (metadata-aware retrieval)."""
    if not allowed_docs:
        return []
    q = re.sub(r"[^a-z0-9 ]", " ", query.lower())
    q = f" {' '.join(q.split())} "
    mentioned = []
    for doc_id, title in db.execute(select(Document.id, Document.title).where(Document.id.in_(allowed_docs))):
        normalized = " ".join(re.sub(r"[^a-z0-9 ]", " ", title.lower()).split())
        if len(normalized) >= 6 and len(normalized.split()) >= 2 and f" {normalized} " in q:
            mentioned.append(doc_id)
    return mentioned


class RetrievalPipeline:
    def __init__(
        self, embedder: EmbeddingService | None = None, reranker: Reranker | None | bool = True
    ) -> None:
        self.embedder = embedder or get_embedding_service()
        self.reranker = get_reranker() if reranker is True else (reranker or None)

    def run(
        self,
        db: Session,
        scope: RetrievalScope,
        query: str,
        config: RetrievalConfig | None = None,
        history: list[tuple[str, str]] | None = None,
    ) -> RetrievalResult:
        cfg = config or RetrievalConfig()
        timer = _Timer()

        with timer.stage("plan"):
            plan = query_processing.plan(query, history, rewrite=cfg.rewrite, multi_query=cfg.multi_query)
        decisions = list(plan.decisions)
        result = RetrievalResult(
            query=query,
            normalized_query=plan.normalized,
            queries=plan.all_queries,
            evidence=[],
            config=cfg,
            decisions=decisions,
            embedding_model=self.embedder.model_version,
        )
        if not plan.normalized:
            result.timings_ms = timer.timings
            return result

        with timer.stage("access"):
            allowed_docs = stores.allowed_document_ids(db, scope)
        if not allowed_docs:
            decisions.append("no searchable documents in scope")
            result.timings_ms = timer.timings
            return result

        rankings: dict[str, list[uuid.UUID]] = {}
        dense_scores: dict[uuid.UUID, float] = {}
        sparse_scores: dict[uuid.UUID, float] = {}
        dense_ranks: dict[uuid.UUID, int] = {}
        sparse_ranks: dict[uuid.UUID, int] = {}
        org_index = None
        if cfg.strategy in ("sparse", "hybrid") or cfg.expansion is not False:
            with timer.stage("sparse_index"):
                org_index = stores.sparse_cache.get(db, scope.org_id)

        chunk_count = (
            org_index.index.n_docs if org_index else stores.sparse_cache.chunk_count(db, scope.org_id)
        )
        for qi, q in enumerate(plan.all_queries):
            if cfg.strategy in ("dense", "hybrid"):
                with timer.stage("embed_query"):
                    vector = self.embedder.embed_query(q)
                with timer.stage("dense"):
                    hits = stores.dense_search(
                        db,
                        scope,
                        allowed_docs,
                        vector,
                        self.embedder.model_version,
                        cfg.candidate_k,
                        cfg.metric,
                        org_chunk_count=chunk_count,
                    )
                rankings[f"dense:{qi}"] = [h[0] for h in hits]
                for rank, (cid, score) in enumerate(hits, start=1):
                    dense_scores[cid] = max(dense_scores.get(cid, -1.0), score)
                    dense_ranks[cid] = min(dense_ranks.get(cid, rank), rank)

            if cfg.strategy in ("sparse", "hybrid") and org_index is not None:
                with timer.stage("sparse"):
                    hits = stores.sparse_search(org_index, allowed_docs, q, cfg.candidate_k)
                    expand = cfg.expansion is True or (
                        cfg.expansion == "auto"
                        and qi == 0
                        and bool(hits)
                        and org_index.index.n_docs >= EXPANSION_MIN_CORPUS
                        and lexical_match_strength(org_index.index, q, hits[0][1]) < EXPANSION_WEAK_MATCH
                    )
                    if expand and hits:
                        expansion = query_processing.pseudo_relevance_feedback(
                            org_index.index, [h[0] for h in hits[:3]], q
                        )
                        if expansion:
                            weighted = {t: 1.0 for t in analyze(q)} | expansion
                            hits = stores.sparse_search(org_index, allowed_docs, weighted, cfg.candidate_k)
                            decisions.append(
                                f"expansion:prf — added {', '.join(sorted(expansion))}"
                                + (" (weak lexical match)" if cfg.expansion == "auto" else "")
                            )
                rankings[f"sparse:{qi}"] = [h[0] for h in hits]
                for rank, (cid, score) in enumerate(hits, start=1):
                    sparse_scores[cid] = max(sparse_scores.get(cid, 0.0), score)
                    sparse_ranks[cid] = min(sparse_ranks.get(cid, rank), rank)

        with timer.stage("fusion"):
            weights = {
                name: (cfg.dense_weight if name.startswith("dense") else cfg.sparse_weight)
                for name in rankings
            }
            if cfg.metadata_boost:
                mentioned = _mentioned_documents(db, allowed_docs, plan.search_query)
                if mentioned:
                    candidates = set().union(*map(set, rankings.values())) if rankings else set()
                    boosted = list(
                        db.scalars(
                            select(DocumentChunk.id).where(
                                DocumentChunk.id.in_(candidates), DocumentChunk.document_id.in_(mentioned)
                            )
                        )
                    )
                    if boosted:
                        order = [cid for cid in rankings[next(iter(rankings))] if cid in set(boosted)]
                        order += [cid for cid in boosted if cid not in set(order)]
                        rankings["metadata"] = order
                        weights["metadata"] = 0.5
                        decisions.append(f"metadata_boost — query names {len(mentioned)} document(s)")
            fused = reciprocal_rank_fusion(rankings, k=cfg.rrf_k, weights=weights)
        result.candidates_considered = len(fused)

        with timer.stage("load"):
            pool_size = cfg.candidate_k if self.reranker is not None and cfg.rerank else cfg.top_k * 3
            pool_ids = [cid for cid, _ in fused[:pool_size]]
            evidence = self._load(db, scope, pool_ids)
            fused_score = dict(fused)
            for item in evidence:
                item.fusion_score = round(fused_score.get(item.chunk_id, 0.0), 6)
                item.dense_score = (
                    round(dense_scores[item.chunk_id], 6) if item.chunk_id in dense_scores else None
                )
                item.sparse_score = (
                    round(sparse_scores[item.chunk_id], 4) if item.chunk_id in sparse_scores else None
                )
                item.dense_rank = dense_ranks.get(item.chunk_id)
                item.sparse_rank = sparse_ranks.get(item.chunk_id)

        if cfg.dedupe:
            with timer.stage("dedupe"):
                evidence, removed = remove_near_duplicates(evidence)
            if removed:
                decisions.append(f"dedupe — removed {removed} near-duplicate passage(s)")

        if cfg.rerank and self.reranker is not None and evidence:
            with timer.stage("rerank"):
                scores = self.reranker.rerank(
                    plan.search_query,
                    [f"{e.context_header}\n{e.content}" if e.context_header else e.content for e in evidence],
                )
            for item, score in zip(evidence, scores, strict=True):
                item.rerank_score = round(score, 4)
            evidence.sort(key=lambda e: e.rerank_score or 0.0, reverse=True)
            result.reranker = self.reranker.name

        if cfg.relevance_threshold is not None:
            before = len(evidence)
            evidence = [e for e in evidence if e.primary_score >= cfg.relevance_threshold]
            if len(evidence) < before:
                decisions.append(
                    f"threshold — dropped {before - len(evidence)} passage(s) below {cfg.relevance_threshold}"
                )

        evidence = evidence[: cfg.top_k]
        for rank, item in enumerate(evidence, start=1):
            item.final_rank = rank

        if cfg.compression and evidence:
            with timer.stage("compression"):
                saved = compress(
                    plan.search_query,
                    evidence,
                    sentence_vectors=self.embedder.embed_documents,
                    query_vector=self.embedder.embed_query(plan.search_query),
                )
            decisions.append(f"compression — removed {saved} characters of low-relevance text")

        result.evidence = evidence
        result.timings_ms = timer.timings
        return result

    @staticmethod
    def _load(db: Session, scope: RetrievalScope, chunk_ids: list[uuid.UUID]) -> list[Evidence]:
        if not chunk_ids:
            return []
        rows = db.execute(
            select(DocumentChunk, Document.title, Document.file_type)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.id.in_(chunk_ids), DocumentChunk.organization_id == scope.org_id)
        ).all()
        by_id = {
            chunk.id: Evidence(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=title,
                file_type=file_type,
                content=chunk.content,
                page_number=chunk.page_number,
                page_end=chunk.page_end,
                section=chunk.section,
                heading_path=list(chunk.heading_path or []),
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                content_hash=chunk.content_hash,
                context_header=(chunk.chunk_metadata or {}).get("context_header", ""),
            )
            for chunk, title, file_type in rows
        }
        return [by_id[cid] for cid in chunk_ids if cid in by_id]


def log_query(
    db: Session,
    scope: RetrievalScope,
    result: RetrievalResult,
    kind: str,
    filters: dict | None = None,
    success: bool | None = None,
) -> SearchQuery:
    top = result.evidence[0].primary_score if result.evidence else None
    row = SearchQuery(
        organization_id=scope.org_id,
        user_id=scope.user_id,
        kind=kind,
        query=result.query[:4000],
        rewritten_queries=[q for q in result.queries if q != result.normalized_query],
        strategy=result.config.strategy,
        config=result.config.to_dict(),
        filters=filters or {},
        result_count=len(result.evidence),
        top_score=top,
        success=bool(result.evidence) if success is None else success,
        timings=result.timings_ms,
        retrieval_ms=result.total_ms,
    )
    db.add(row)
    return row
