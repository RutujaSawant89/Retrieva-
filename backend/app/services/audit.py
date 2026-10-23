"""Audit logging for security-relevant actions."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import correlation_id_var
from app.db.models import AuditLog


def record(
    db: Session,
    *,
    org_id: uuid.UUID,
    action: str,
    user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: object | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            organization_id=org_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:255] or None,
            correlation_id=correlation_id_var.get(),
            details=details or {},
        )
    )
