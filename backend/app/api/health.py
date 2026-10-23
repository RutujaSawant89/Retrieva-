from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest, multiprocess
from sqlalchemy import text

from app.core.config import get_settings
from app.core.redis import get_redis
from app.db.session import get_engine

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready() -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        logger.warning("readiness_db_failed", exc_info=True)
        checks["database"] = "error"
    if get_settings().redis_url:
        checks["redis"] = "ok" if get_redis() is not None else "unavailable"
    healthy = checks["database"] == "ok"
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        # Aggregate samples written by every API worker process.
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
