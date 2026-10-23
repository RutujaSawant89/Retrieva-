from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import AuthUser, CurrentUser, DbSession, require
from app.core.permissions import Permission
from app.services import analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])

Analyst = Annotated[CurrentUser, Depends(require(Permission.ANALYTICS_READ))]


@router.get("/overview")
def overview(current: AuthUser, db: DbSession) -> dict[str, Any]:
    """Headline counts for the dashboard. Available to every member of the organization."""
    return analytics.overview(db, current.org_id)


@router.get("/retrieval")
def retrieval(current: Analyst, db: DbSession, days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    return analytics.retrieval(db, current.org_id, days)


@router.get("/usage")
def usage(current: Analyst, db: DbSession, days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    return analytics.usage(db, current.org_id, days)
