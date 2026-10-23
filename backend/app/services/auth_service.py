"""Registration, login, refresh-token rotation and organization switching."""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConflictError, PermissionDeniedError, ValidationFailedError
from app.core.permissions import ROLE_IDS, RoleName, permissions_for
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    password_needs_rehash,
    validate_password_strength,
    verify_password,
)
from app.db import tenancy
from app.db.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMember,
    RefreshToken,
    Role,
    User,
)
from app.schemas.auth import OrganizationSummary, SessionOut, UserOut
from app.services import audit


@dataclass
class IssuedSession:
    body: SessionOut
    refresh_token: str
    refresh_expires_at: datetime


@dataclass
class ClientInfo:
    ip: str | None = None
    user_agent: str | None = None


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "org"
    return f"{base}-{secrets.token_hex(3)}"


def _now() -> datetime:
    return datetime.now(UTC)


def list_memberships(db: Session, user_id: uuid.UUID) -> list[OrganizationSummary]:
    rows = db.execute(
        select(Organization, Role.name)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .join(Role, Role.id == OrganizationMember.role_id)
        .where(OrganizationMember.user_id == user_id, Organization.deleted_at.is_(None))
        .order_by(OrganizationMember.created_at)
    ).all()
    return [OrganizationSummary(id=o.id, name=o.name, slug=o.slug, role=r) for o, r in rows]


def _issue(
    db: Session, user: User, org_id: uuid.UUID, client: ClientInfo, family_id: uuid.UUID | None = None
) -> IssuedSession:
    settings = get_settings()
    orgs = list_memberships(db, user.id)
    current = next((o for o in orgs if o.id == org_id), None)
    if current is None:
        raise PermissionDeniedError("You are not a member of this organization")

    access, access_exp = create_access_token(user.id, org_id, current.role)
    raw_refresh = new_opaque_token()
    refresh_exp = _now() + timedelta(days=settings.refresh_token_ttl_days)
    token_row = RefreshToken(
        user_id=user.id,
        organization_id=org_id,
        token_hash=hash_token(raw_refresh),
        family_id=family_id or uuid.uuid4(),
        expires_at=refresh_exp,
        user_agent=(client.user_agent or "")[:255] or None,
        ip_address=client.ip,
    )
    db.add(token_row)
    db.flush()
    body = SessionOut(
        access_token=access,
        expires_at=access_exp,
        user=UserOut.model_validate(user),
        organization=current,
        organizations=orgs,
        permissions=sorted(p.value for p in permissions_for(current.role)),
    )
    return IssuedSession(body=body, refresh_token=raw_refresh, refresh_expires_at=refresh_exp)


def register(
    db: Session,
    *,
    email: str,
    full_name: str,
    password: str,
    organization_name: str | None,
    invitation_token: str | None,
    client: ClientInfo,
) -> IssuedSession:
    settings = get_settings()
    email = email.strip().lower()
    problems = validate_password_strength(password, email=email)
    if problems:
        raise ValidationFailedError(
            "Password does not meet the policy",
            details={"fields": [{"field": "password", "message": f"Password {p}"} for p in problems]},
        )

    invitation: OrganizationInvitation | None = None
    if invitation_token:
        invitation = db.scalar(
            select(OrganizationInvitation).where(
                OrganizationInvitation.token_hash == hash_token(invitation_token),
                OrganizationInvitation.accepted_at.is_(None),
                OrganizationInvitation.expires_at > _now(),
            )
        )
        if invitation is None or invitation.email.lower() != email:
            raise ValidationFailedError("Invitation is invalid, expired, or for a different email address")
    elif not organization_name:
        raise ValidationFailedError("organization_name is required when registering without an invitation")
    elif not settings.allow_open_registration:
        raise PermissionDeniedError("Open registration is disabled; ask an administrator for an invitation")

    if db.scalar(select(User.id).where(func.lower(User.email) == email)) is not None:
        raise ConflictError("An account with this email already exists")

    user = User(email=email, full_name=full_name, password_hash=hash_password(password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:  # concurrent registration with the same email
        raise ConflictError("An account with this email already exists") from exc

    if invitation is not None:
        org_id = invitation.organization_id
        db.add(OrganizationMember(organization_id=org_id, user_id=user.id, role_id=invitation.role_id))
        invitation.accepted_at = _now()
        action = "auth.register_invited"
    else:
        org = Organization(name=organization_name or "", slug=_slugify(organization_name or "org"))
        db.add(org)
        db.flush()
        org_id = org.id
        db.add(OrganizationMember(organization_id=org_id, user_id=user.id, role_id=ROLE_IDS[RoleName.ADMIN]))
        action = "auth.register"
    db.flush()

    user.last_login_at = _now()
    tenancy.bind_tenant(db, org_id)
    audit.record(
        db,
        org_id=org_id,
        user_id=user.id,
        action=action,
        resource_type="user",
        resource_id=user.id,
        ip_address=client.ip,
        user_agent=client.user_agent,
    )
    return _issue(db, user, org_id, client)


def login(
    db: Session, *, email: str, password: str, organization_id: uuid.UUID | None, client: ClientInfo
) -> IssuedSession:
    user = db.scalar(
        select(User).where(func.lower(User.email) == email.strip().lower(), User.deleted_at.is_(None))
    )
    # verify_password runs even for unknown users so response timing does not reveal accounts.
    if not verify_password(password, user.password_hash if user else None) or user is None:
        raise AuthenticationError("Invalid email or password")
    if not user.is_active:
        raise AuthenticationError("This account is disabled")
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    orgs = list_memberships(db, user.id)
    if not orgs:
        raise AuthenticationError("This account does not belong to any organization")
    org_id = organization_id or orgs[0].id
    user.last_login_at = _now()
    issued = _issue(db, user, org_id, client)
    tenancy.bind_tenant(db, org_id)
    audit.record(
        db,
        org_id=org_id,
        user_id=user.id,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        ip_address=client.ip,
        user_agent=client.user_agent,
    )
    return issued


def refresh(
    db: Session, raw_token: str | None, client: ClientInfo, org_id: uuid.UUID | None = None
) -> IssuedSession:
    """Rotate a refresh token. Presenting an already-rotated token revokes the whole family."""
    if not raw_token:
        raise AuthenticationError("Missing refresh token")
    token = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)).with_for_update()
    )
    if token is None:
        raise AuthenticationError("Invalid refresh token")
    if token.revoked_at is not None:
        successor = db.get(RefreshToken, token.replaced_by_id) if token.replaced_by_id else None
        if successor is not None and successor.revoked_at is None and successor.expires_at > _now():
            # The rotated token's successor was never used: the client did not receive it
            # (lost response, navigation mid-request) or another tab refreshed concurrently.
            # Supersede the unused successor instead of treating this as theft.
            successor.revoked_at = _now()
            issued = _rotate(db, token, client, org_id)
            # Whichever of the two cookies the browser ends up keeping must stay recoverable.
            successor.replaced_by_id = token.replaced_by_id
            return issued
        # The successor chain moved on, so an old token is being replayed: likely theft.
        # Invalidate every token in the family.
        revoked = db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == token.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        ).rowcount
        if revoked:
            tenancy.bind_tenant(db, token.organization_id)
            audit.record(
                db,
                org_id=token.organization_id,
                user_id=token.user_id,
                action="auth.refresh_reuse_detected",
                ip_address=client.ip,
                user_agent=client.user_agent,
                details={"family_id": str(token.family_id)},
            )
            db.commit()
        raise AuthenticationError("Refresh token has already been used; please sign in again")
    if token.expires_at <= _now():
        raise AuthenticationError("Refresh token expired")
    return _rotate(db, token, client, org_id)


def _rotate(db: Session, token: RefreshToken, client: ClientInfo, org_id: uuid.UUID | None) -> IssuedSession:
    user = db.get(User, token.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise AuthenticationError("Account is not active")
    issued = _issue(db, user, org_id or token.organization_id, client, family_id=token.family_id)
    token.revoked_at = token.revoked_at or _now()
    token.replaced_by_id = db.scalar(
        select(RefreshToken.id).where(RefreshToken.token_hash == hash_token(issued.refresh_token))
    )
    return issued


def logout(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if token is not None:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == token.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        tenancy.bind_tenant(db, token.organization_id)
        audit.record(db, org_id=token.organization_id, user_id=token.user_id, action="auth.logout")


def change_password(db: Session, user: User, org_id: uuid.UUID, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise AuthenticationError("Current password is incorrect")
    problems = validate_password_strength(new, email=user.email)
    if problems:
        raise ValidationFailedError(
            "Password does not meet the policy",
            details={"fields": [{"field": "new_password", "message": f"Password {p}"} for p in problems]},
        )
    user.password_hash = hash_password(new)
    # Sign out every other session.
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    audit.record(db, org_id=org_id, user_id=user.id, action="auth.password_changed")
