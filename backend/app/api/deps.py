"""FastAPI dependencies: DB sessions, authentication, tenant binding and permission checks."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.permissions import Permission, RoleName, has_permission
from app.core.rate_limit import rate_limiter
from app.core.security import TokenError, decode_access_token
from app.db import tenancy
from app.db.models import OrganizationMember, User
from app.db.session import get_session_factory

_bearer = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class CurrentUser:
    user: User
    org_id: uuid.UUID
    role: str

    @property
    def id(self) -> uuid.UUID:
        return self.user.id

    @property
    def is_admin(self) -> bool:
        return self.role == RoleName.ADMIN

    def can(self, permission: Permission) -> bool:
        return has_permission(self.role, permission)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def get_current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Authentication required")
    try:
        claims = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise AuthenticationError("Invalid or expired access token") from exc

    # Membership is re-checked on every request so removed members lose access immediately,
    # and role changes take effect without waiting for the access token to expire.
    row = db.execute(
        select(User, OrganizationMember)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(
            User.id == claims.user_id,
            OrganizationMember.organization_id == claims.org_id,
            User.deleted_at.is_(None),
        )
    ).first()
    if row is None or not row[0].is_active:
        raise AuthenticationError("Account is not active in this organization")
    user, membership = row

    tenancy.bind_tenant(db, claims.org_id)
    request.state.usage = {"org_id": claims.org_id, "user_id": user.id}
    rate_limiter.hit(f"user:{user.id}", get_settings().rate_limit_per_minute)
    return CurrentUser(user=user, org_id=claims.org_id, role=membership.role.name)


AuthUser = Annotated[CurrentUser, Depends(get_current_user)]


def require(permission: Permission) -> Callable[[CurrentUser], CurrentUser]:
    def checker(current: AuthUser) -> CurrentUser:
        if not current.can(permission):
            raise PermissionDeniedError(f"Your role does not allow '{permission.value}'")
        return current

    return checker
