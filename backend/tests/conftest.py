"""Test harness.

Tests run against a real PostgreSQL + pgvector database so that Row-Level Security, vector
search and constraints are exercised exactly as in production.

* In CI, ``TEST_DATABASE_ADMIN_URL`` points at a pgvector service container.
* Locally, an embedded server (``pgserver``) is started automatically.

Migrations run as the admin (superuser) role; the application connects as ``retrieva_app``,
a non-superuser without BYPASSRLS, so RLS policies are genuinely enforced in tests.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

TEST_DB = "retrieva_test"
APP_ROLE = "retrieva_app"
APP_PASSWORD = "retrieva_app_test"
_DATA_DIR = Path(__file__).resolve().parents[1] / ".pgdata"


def _admin_base_url() -> str:
    """Admin URL (psycopg form, no driver suffix) for the maintenance database."""
    url = os.environ.get("TEST_DATABASE_ADMIN_URL")
    if url:
        return url.replace("postgresql+psycopg://", "postgresql://")
    import pgserver

    server = pgserver.get_server(_DATA_DIR, cleanup_mode=None)
    return server.get_uri("postgres")


def _with_db(url: str, db: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{db}"


def _prepare_database() -> tuple[str, str]:
    admin = _admin_base_url()
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN "
            f"CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}' NOSUPERUSER NOBYPASSRLS; END IF; END $$;"
        )
        conn.execute(f"ALTER ROLE {APP_ROLE} WITH PASSWORD '{APP_PASSWORD}'")
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (TEST_DB,),
        )
        conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}"')
        conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    admin_db = _with_db(admin, TEST_DB)
    host_part = admin_db.split("@", 1)[1]
    app_db = f"postgresql://{APP_ROLE}:{APP_PASSWORD}@{host_part}"
    return admin_db, app_db


_ADMIN_URL, _APP_URL = _prepare_database()
_STORAGE = Path(tempfile.mkdtemp(prefix="retrieva-test-storage-"))

os.environ.update(
    {
        "ENVIRONMENT": "test",
        "LOG_JSON": "false",
        "LOG_LEVEL": "WARNING",
        "DATABASE_URL": _APP_URL.replace("postgresql://", "postgresql+psycopg://"),
        "MIGRATION_DATABASE_URL": _ADMIN_URL.replace("postgresql://", "postgresql+psycopg://"),
        "REDIS_URL": "",
        "CELERY_TASK_ALWAYS_EAGER": "true",
        "INGESTION_MODE": "inline",
        "STORAGE_DIR": str(_STORAGE),
        "EMBEDDING_PROVIDER": "hashing",
        "EMBEDDING_MODEL": "hashing-v1",
        "RERANKER_PROVIDER": "lexical",
        "LLM_PROVIDER": "extractive",
        "JWT_SECRET": "test-secret-0123456789abcdef0123456789abcdef",
        "RATE_LIMIT_PER_MINUTE": "100000",
        "AUTH_RATE_LIMIT_PER_MINUTE": "100000",
        "METRICS_ENABLED": "true",
    }
)


def _run_migrations() -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    command.upgrade(cfg, "head")


_run_migrations()

# Tables that tests may write to; truncated between tests (roles are seed data and kept).
_TRUNCATE = (
    "organizations, users, organization_members, organization_invitations, refresh_tokens, documents, "
    "document_chunks, document_collections, collection_documents, conversations, messages, "
    "message_citations, ingestion_jobs, search_queries, evaluation_datasets, evaluation_runs, "
    "evaluation_results, audit_logs, api_usage"
)


@pytest.fixture(autouse=True)
def _clean_database() -> Iterator[None]:
    yield
    with psycopg.connect(_ADMIN_URL, autocommit=True) as conn:
        conn.execute(f"TRUNCATE {_TRUNCATE} CASCADE")
    from app.core.rate_limit import rate_limiter

    rate_limiter.reset()


@pytest.fixture
def admin_db_url() -> str:
    return _ADMIN_URL


@pytest.fixture
def client() -> Iterator:
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


STRONG_PASSWORD = "Sup3r-Secret-Pass!"


def register(client, email: str, org: str | None = "Acme Research", **extra) -> dict:  # type: ignore[no-untyped-def]
    body = {"email": email, "full_name": email.split("@")[0].title(), "password": STRONG_PASSWORD}
    if org is not None:
        body["organization_name"] = org
    body.update(extra)
    response = client.post("/api/v1/auth/register", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['access_token']}"}


@pytest.fixture
def admin_session(client) -> dict:  # type: ignore[no-untyped-def]
    return register(client, "admin@acme.example.com")
