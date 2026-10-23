"""Engine and session factory."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db import tenancy


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        future=True,
        # Day bucketing (date_trunc) and timestamps must agree with the API's UTC clock.
        # "GMT" is built into PostgreSQL and works even on builds without a tz database.
        connect_args={"options": "-c timezone=GMT"},
    )
    return engine


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)
    event.listen(factory, "after_begin", tenancy.apply_tenant_on_begin)
    return factory


@contextmanager
def session_scope(org_id: object | None = None) -> Iterator[Session]:
    """Transactional scope for workers and scripts. Commits on success, rolls back on error."""
    session = get_session_factory()()
    try:
        if org_id is not None:
            tenancy.bind_tenant(session, org_id)
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
