"""Dispatch ingestion jobs according to ``INGESTION_MODE``."""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None


def _thread_pool() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ingestion")
    return _executor


def dispatch_ingestion(document_id: uuid.UUID, org_id: uuid.UUID, job_id: uuid.UUID) -> str | None:
    """Start processing a document. Returns the Celery task id when a worker queue is used.

    Must be called after the transaction that created the document/job has committed.
    """
    from app.services.ingestion.pipeline import run_ingestion

    mode = get_settings().ingestion_mode
    if mode == "inline":
        run_ingestion(document_id, org_id, job_id)
        return None
    if mode == "celery":
        try:
            from app.workers.tasks import ingest_document

            result = ingest_document.delay(str(document_id), str(org_id), str(job_id))
            return result.id
        except Exception:
            # Broker unreachable: process in-process rather than leaving the job stranded.
            logger.exception("celery_dispatch_failed_falling_back_to_thread")
    _thread_pool().submit(run_ingestion, document_id, org_id, job_id)
    return None


def dispatch_evaluation(run_id: uuid.UUID, org_id: uuid.UUID) -> str | None:
    """Start an evaluation run (same execution modes as ingestion)."""
    from app.services.evaluation.runner import run_evaluation

    mode = get_settings().ingestion_mode
    if mode == "inline":
        run_evaluation(run_id, org_id)
        return None
    if mode == "celery":
        try:
            from app.workers.tasks import run_evaluation_task

            return run_evaluation_task.delay(str(run_id), str(org_id)).id
        except Exception:
            logger.exception("celery_dispatch_failed_falling_back_to_thread")
    _thread_pool().submit(run_evaluation, run_id, org_id)
    return None
