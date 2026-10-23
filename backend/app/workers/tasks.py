from __future__ import annotations

import uuid

from sqlalchemy.exc import OperationalError

from app.workers.celery_app import celery_app


@celery_app.task(
    name="retrieva.ingest_document",
    autoretry_for=(OperationalError,),  # transient database errors
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def ingest_document(document_id: str, org_id: str, job_id: str) -> None:
    from app.services.ingestion.pipeline import run_ingestion

    run_ingestion(uuid.UUID(document_id), uuid.UUID(org_id), uuid.UUID(job_id))


@celery_app.task(name="retrieva.run_evaluation")
def run_evaluation_task(run_id: str, org_id: str) -> None:
    from app.services.evaluation.runner import run_evaluation

    run_evaluation(uuid.UUID(run_id), uuid.UUID(org_id))
