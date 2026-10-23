"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import health
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.telemetry import setup_tracing
from app.db.session import get_engine

logger = logging.getLogger(__name__)


def _warn_if_rls_bypassed() -> None:
    """RLS is silently skipped for superusers / BYPASSRLS roles; make that visible."""
    try:
        with get_engine().connect() as conn:
            row = conn.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            ).first()
        if row and (row[0] or row[1]):
            logger.warning(
                "database_role_bypasses_rls",
                extra={"hint": "Connect the API as the non-superuser 'retrieva_app' role so RLS is enforced"},
            )
    except Exception:
        logger.warning("database_unreachable_at_startup", exc_info=True)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    app = FastAPI(
        title="Retrieva API",
        version="0.1.0",
        description="Enterprise AI Retrieval & Intelligence Platform — evidence-grounded RAG.",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    register_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
        expose_headers=["X-Correlation-ID"],
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    app.include_router(api_router, prefix=settings.api_prefix)
    setup_tracing(app, settings)
    return app


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if get_settings().environment != "test":
        await anyio.to_thread.run_sync(_warn_if_rls_bypassed)
    yield


app = create_app()
