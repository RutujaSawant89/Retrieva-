"""Document ingestion pipeline: extract → clean → chunk → embed → index.

Each stage commits its status so the UI can show live progress. The pipeline is idempotent:
re-running it replaces the document's chunks. Failures mark the document and job ``failed``
with a user-safe message; the full traceback goes to the logs.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.metrics import INGESTION_JOBS
from app.db.models import Document, DocumentChunk, DocumentStatus, IngestionJob
from app.db.session import session_scope
from app.services import storage
from app.services.embeddings.service import EmbeddingError, content_hash, get_embedding_service
from app.services.ingestion.chunking import ChunkingConfig, chunk_document
from app.services.ingestion.cleaning import clean_blocks
from app.services.ingestion.extractors import ExtractionError, extract
from app.services.ingestion.types import Chunk, ExtractedDocument

logger = logging.getLogger(__name__)

EMBED_BATCH = 64


class IngestionFailure(Exception):
    """A failure with a message that is safe to show to users."""


def chunking_config_from(job_config: dict) -> ChunkingConfig:
    settings = get_settings()
    return ChunkingConfig(
        strategy=job_config.get("strategy", settings.chunking_strategy),
        chunk_size=int(job_config.get("chunk_size", settings.chunk_size)),
        chunk_overlap=int(job_config.get("chunk_overlap", settings.chunk_overlap)),
        max_tokens=int(job_config.get("max_tokens", settings.chunk_max_tokens)),
    )


def contextualize(chunk: Chunk, title: str) -> str:
    """Text that is embedded and BM25-indexed: the chunk prefixed with its document context.

    Prepending the title and heading path ("contextual chunk headers") lets a chunk such as
    "The notice period is 90 days" be found by a query that names the agreement or section.
    """
    header = " > ".join([title, *chunk.heading_path]) if chunk.heading_path else title
    return f"{header}\n\n{chunk.text}"


class _Progress:
    def __init__(self, session: Session, document: Document, job: IngestionJob) -> None:
        self.session = session
        self.document = document
        self.job = job
        self.stage_started = time.perf_counter()
        self.stage: DocumentStatus | None = None

    def enter(self, stage: DocumentStatus, progress: int) -> None:
        self._close_stage()
        self.stage = stage
        self.stage_started = time.perf_counter()
        self.set(progress, stage)

    def set(self, progress: int, stage: DocumentStatus | None = None) -> None:
        if stage is not None:
            self.document.status = stage
            self.job.status = stage
        self.document.progress = progress
        self.job.progress = progress
        self.session.commit()

    def _close_stage(self) -> None:
        if self.stage is not None:
            timings = dict(self.job.stage_timings or {})
            timings[self.stage.value] = round((time.perf_counter() - self.stage_started) * 1000, 1)
            self.job.stage_timings = timings

    def finish(self) -> None:
        self._close_stage()


def run_ingestion(document_id: uuid.UUID, org_id: uuid.UUID, job_id: uuid.UUID | None = None) -> None:
    """Process one document. Safe to call from Celery workers, threads, or inline."""
    with session_scope(org_id) as session:
        document = session.get(Document, document_id)
        if document is None or document.deleted_at is not None:
            logger.info("ingestion_skipped_missing_document", extra={"document_id": str(document_id)})
            return
        job = session.get(IngestionJob, job_id) if job_id else None
        if job is None:
            job = session.scalar(
                select(IngestionJob)
                .where(IngestionJob.document_id == document_id)
                .order_by(IngestionJob.created_at.desc())
                .limit(1)
            )
        if job is None:
            job = IngestionJob(organization_id=org_id, document_id=document_id, config={})
            session.add(job)
        job.attempts = (job.attempts or 0) + 1
        job.started_at = datetime.now(UTC)
        job.error_message = None
        document.error_message = None
        progress = _Progress(session, document, job)

        try:
            _process(session, document, job, progress)
            progress.finish()
            document.status = job.status = DocumentStatus.COMPLETED
            document.progress = job.progress = 100
            document.indexed_at = job.finished_at = datetime.now(UTC)
            session.commit()
            INGESTION_JOBS.labels("completed").inc()
            logger.info(
                "ingestion_completed",
                extra={
                    "document_id": str(document_id),
                    "chunks": document.chunk_count,
                    "timings_ms": job.stage_timings,
                },
            )
        except Exception as exc:
            session.rollback()
            message = (
                str(exc)
                if isinstance(exc, IngestionFailure | ExtractionError | EmbeddingError)
                else ("Processing failed due to an internal error")
            )
            logger.exception("ingestion_failed", extra={"document_id": str(document_id)})
            document = session.get(Document, document_id)
            job = session.get(IngestionJob, job.id)
            if document is not None:
                document.status = DocumentStatus.FAILED
                document.error_message = message[:1000]
            if job is not None:
                job.status = DocumentStatus.FAILED
                job.error_message = message[:1000]
                job.finished_at = datetime.now(UTC)
            session.commit()
            INGESTION_JOBS.labels("failed").inc()


def _process(session: Session, document: Document, job: IngestionJob, progress: _Progress) -> None:
    embedder = get_embedding_service()

    # 1. Extraction + cleaning ------------------------------------------------------------
    progress.enter(DocumentStatus.EXTRACTING, 10)
    try:
        data = storage.resolve(document.storage_path).read_bytes()
    except FileNotFoundError as exc:
        raise IngestionFailure("The stored file is missing") from exc
    extracted: ExtractedDocument = extract(document.file_type, data)
    extracted.blocks = clean_blocks(extracted.blocks)
    extracted.finalize()
    if not extracted.full_text.strip():
        hint = (
            " The PDF appears to be scanned; configure an OCR engine to process it."
            if extracted.metadata.get("pages_without_text")
            else ""
        )
        raise IngestionFailure("No extractable text was found in the document." + hint)
    storage.extracted_path(document.storage_path).write_text(
        json.dumps(extracted.to_json(), ensure_ascii=False), encoding="utf-8"
    )
    document.page_count = extracted.page_count
    meta = dict(document.doc_metadata or {})
    meta.update({k: v for k, v in extracted.metadata.items() if k != "title"})
    if extracted.metadata.get("title"):
        meta["extracted_title"] = extracted.metadata["title"]
    meta["characters"] = len(extracted.full_text)
    document.doc_metadata = meta

    # 2. Chunking --------------------------------------------------------------------------
    progress.enter(DocumentStatus.CHUNKING, 30)
    cfg = chunking_config_from(job.config or {})
    try:
        chunks = chunk_document(
            extracted,
            cfg,
            count=embedder.provider.count_tokens,
            embed=embedder.embed_documents if cfg.strategy == "semantic" else None,
        )
    except ValueError as exc:
        raise IngestionFailure(f"Invalid chunking configuration: {exc}") from exc
    if not chunks:
        raise IngestionFailure("The document produced no chunks")

    # 3. Embedding (with reuse of unchanged content) ----------------------------------------
    progress.enter(DocumentStatus.EMBEDDING, 40)
    texts = [contextualize(c, document.title) for c in chunks]
    hashes = [content_hash(t) for t in texts]
    vectors_parts = []
    reused_total = 0
    for start in range(0, len(texts), EMBED_BATCH):
        vectors, reused = embedder.embed_documents_with_reuse(
            session,
            document.organization_id,
            texts[start : start + EMBED_BATCH],
            hashes[start : start + EMBED_BATCH],
        )
        vectors_parts.append(vectors)
        reused_total += reused
        done = min(len(texts), start + EMBED_BATCH)
        progress.set(40 + int(45 * done / len(texts)))

    # 4. Indexing ----------------------------------------------------------------------------
    progress.enter(DocumentStatus.INDEXING, 90)
    session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    model_version = embedder.model_version
    row = 0
    for part in vectors_parts:
        for vector in part:
            chunk = chunks[row]
            session.add(
                DocumentChunk(
                    organization_id=document.organization_id,
                    document_id=document.id,
                    chunk_index=chunk.index,
                    content=chunk.text,
                    content_hash=hashes[row],
                    token_count=chunk.token_count,
                    page_number=chunk.page_start,
                    page_end=chunk.page_end,
                    section=(chunk.section or "")[:500] or None,
                    heading_path=[h[:500] for h in chunk.heading_path],
                    start_char=chunk.start,
                    end_char=chunk.end,
                    embedding=vector.tolist(),
                    embedding_model=model_version,
                    chunk_metadata={"context_header": texts[row].split("\n\n", 1)[0]},
                )
            )
            row += 1
    document.chunk_count = len(chunks)
    document.embedding_model = model_version
    document.chunking_strategy = cfg.strategy
    job.config = {
        **(job.config or {}),
        "strategy": cfg.strategy,
        "chunk_size": cfg.chunk_size,
        "chunk_overlap": cfg.chunk_overlap,
        "max_tokens": cfg.max_tokens,
        "embedding_model": model_version,
        "reused_embeddings": reused_total,
    }
    session.flush()
