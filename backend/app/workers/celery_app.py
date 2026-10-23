"""Celery application. Start a worker with::

celery -A app.workers.celery_app worker --loglevel=INFO --concurrency=2
"""

from __future__ import annotations

import contextlib
import os

from celery import Celery
from celery.signals import worker_init, worker_process_init
from prometheus_client import CollectorRegistry, multiprocess, start_http_server

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()

celery_app = Celery("retrieva", broker=settings.broker_url, backend=settings.redis_url or None)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,  # a crashed worker's job is redelivered
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # long CPU-bound jobs: do not hoard tasks
    task_always_eager=settings.celery_task_always_eager,
    task_time_limit=60 * 60,
    task_soft_time_limit=55 * 60,
    broker_connection_retry_on_startup=True,
    result_expires=24 * 3600,
    task_routes={
        "retrieva.ingest_document": {"queue": "ingestion"},
        "retrieva.run_evaluation": {"queue": "evaluation"},
    },
    imports=("app.workers.tasks",),
)


@worker_process_init.connect
def _init_worker_process(**_: object) -> None:
    configure_logging(settings.log_level, settings.log_json)


@worker_init.connect
def _init_worker(**_: object) -> None:
    """Serve Prometheus metrics from the main worker process.

    With ``PROMETHEUS_MULTIPROC_DIR`` set, every pool process writes its samples to that
    directory and this endpoint aggregates them, so one fixed port covers the whole worker.
    """
    configure_logging(settings.log_level, settings.log_json)
    if not settings.metrics_enabled:
        return
    port = int(os.environ.get("WORKER_METRICS_PORT", "9101"))
    registry = None
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    with contextlib.suppress(OSError):  # port already in use: metrics are optional
        start_http_server(port, registry=registry) if registry else start_http_server(port)
