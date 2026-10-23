from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select, update

from app.api.deps import CurrentUser, DbSession, client_ip, require
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.permissions import (
    ROLE_DESCRIPTIONS,
    ROLE_IDS,
    Permission,
    RoleName,
    permissions_for,
)
from app.core.security import hash_token, new_opaque_token
from app.db.models import (
    AuditLog,
    Organization,
    OrganizationInvitation,
    OrganizationMember,
    RefreshToken,
    Role,
    User,
)
from app.schemas.admin import (
    AuditLogOut,
    InvitationCreate,
    InvitationOut,
    MemberOut,
    MemberRoleUpdate,
    OrganizationOut,
    OrganizationUpdate,
    RoleOut,
)
from app.schemas.common import Message, Page
from app.services import audit

router = APIRouter(prefix="/admin", tags=["administration"])

Admin = Annotated[CurrentUser, Depends(require(Permission.MEMBERS_MANAGE))]
Auditor = Annotated[CurrentUser, Depends(require(Permission.AUDIT_READ))]

INVITATION_TTL = timedelta(days=7)


@router.get("/roles", response_model=list[RoleOut])
def list_roles(_: Admin) -> list[RoleOut]:
    return [
        RoleOut(
            name=r.value,
            description=ROLE_DESCRIPTIONS[r],
            permissions=sorted(p.value for p in permissions_for(r)),
        )
        for r in RoleName
    ]


@router.get("/organization", response_model=OrganizationOut)
def get_organization(current: Admin, db: DbSession) -> OrganizationOut:
    org = db.get(Organization, current.org_id)
    if org is None:
        raise NotFoundError("Organization not found")
    return OrganizationOut.model_validate(org)


@router.patch("/organization", response_model=OrganizationOut)
def update_organization(
    body: OrganizationUpdate, current: Admin, request: Request, db: DbSession
) -> OrganizationOut:
    org = db.get(Organization, current.org_id)
    if org is None:
        raise NotFoundError("Organization not found")
    old = org.name
    org.name = body.name.strip()
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="organization.updated",
        resource_type="organization",
        resource_id=org.id,
        ip_address=client_ip(request),
        details={"old_name": old, "new_name": org.name},
    )
    db.flush()
    return OrganizationOut.model_validate(org)


@router.get("/users", response_model=Page[MemberOut])
def list_users(
    current: Admin,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    q: str | None = Query(None, max_length=200),
) -> Page[MemberOut]:
    stmt = (
        select(User, OrganizationMember, Role.name)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .join(Role, Role.id == OrganizationMember.role_id)
        .where(OrganizationMember.organization_id == current.org_id, User.deleted_at.is_(None))
    )
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(User.email).like(like) | func.lower(User.full_name).like(like))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(OrganizationMember.created_at).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [
        MemberOut(
            user_id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=role,
            is_active=u.is_active,
            joined_at=m.created_at,
            last_login_at=u.last_login_at,
        )
        for u, m, role in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


def _membership(db: DbSession, org_id: uuid.UUID, user_id: uuid.UUID) -> OrganizationMember:
    member = db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id, OrganizationMember.user_id == user_id
        )
    )
    if member is None:
        raise NotFoundError("Member not found")
    return member


def _ensure_another_admin(db: DbSession, org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    admins = db.scalar(
        select(func.count()).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.role_id == ROLE_IDS[RoleName.ADMIN],
            OrganizationMember.user_id != user_id,
        )
    )
    if not admins:
        raise ConflictError("An organization must keep at least one admin")


@router.patch("/users/{user_id}", response_model=Message)
def update_member_role(
    user_id: uuid.UUID, body: MemberRoleUpdate, current: Admin, request: Request, db: DbSession
) -> Message:
    member = _membership(db, current.org_id, user_id)
    new_role_id = ROLE_IDS[RoleName(body.role)]
    if member.role_id == ROLE_IDS[RoleName.ADMIN] and new_role_id != member.role_id:
        _ensure_another_admin(db, current.org_id, user_id)
    old_role = member.role.name
    member.role_id = new_role_id
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="member.role_changed",
        resource_type="user",
        resource_id=user_id,
        ip_address=client_ip(request),
        details={"from": old_role, "to": body.role},
    )
    return Message(message="Role updated")


@router.delete("/users/{user_id}", response_model=Message)
def remove_member(user_id: uuid.UUID, current: Admin, request: Request, db: DbSession) -> Message:
    member = _membership(db, current.org_id, user_id)
    if member.role_id == ROLE_IDS[RoleName.ADMIN]:
        _ensure_another_admin(db, current.org_id, user_id)
    db.delete(member)
    # Revoke refresh tokens scoped to this organization.
    db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.organization_id == current.org_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="member.removed",
        resource_type="user",
        resource_id=user_id,
        ip_address=client_ip(request),
    )
    return Message(message="Member removed")


def _invitation_out(inv: OrganizationInvitation, token: str | None = None) -> InvitationOut:
    return InvitationOut(
        id=inv.id,
        email=inv.email,
        role=inv.role.name,
        expires_at=inv.expires_at,
        accepted_at=inv.accepted_at,
        created_at=inv.created_at,
        token=token,
    )


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(current: Admin, db: DbSession) -> list[InvitationOut]:
    rows = db.scalars(
        select(OrganizationInvitation)
        .where(OrganizationInvitation.organization_id == current.org_id)
        .order_by(OrganizationInvitation.created_at.desc())
        .limit(200)
    ).all()
    return [_invitation_out(inv) for inv in rows]


@router.post("/invitations", response_model=InvitationOut, status_code=status.HTTP_201_CREATED)
def create_invitation(
    body: InvitationCreate, current: Admin, request: Request, db: DbSession
) -> InvitationOut:
    email = body.email.lower()
    existing_member = db.scalar(
        select(User.id)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(OrganizationMember.organization_id == current.org_id, func.lower(User.email) == email)
    )
    if existing_member:
        raise ConflictError("This person is already a member")
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        # Existing accounts are added directly; invitations are for new sign-ups.
        raise ValidationFailedError(
            "An account with this email already exists; ask them to share their account or use a new email"
        )
    token = new_opaque_token()
    inv = OrganizationInvitation(
        organization_id=current.org_id,
        email=email,
        role_id=ROLE_IDS[RoleName(body.role)],
        token_hash=hash_token(token),
        invited_by=current.id,
        expires_at=datetime.now(UTC) + INVITATION_TTL,
    )
    db.add(inv)
    db.flush()
    db.refresh(inv)
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="member.invited",
        resource_type="invitation",
        resource_id=inv.id,
        ip_address=client_ip(request),
        details={"email": email, "role": body.role},
    )
    return _invitation_out(inv, token)


@router.delete("/invitations/{invitation_id}", response_model=Message)
def revoke_invitation(invitation_id: uuid.UUID, current: Admin, request: Request, db: DbSession) -> Message:
    inv = db.scalar(
        select(OrganizationInvitation).where(
            OrganizationInvitation.id == invitation_id,
            OrganizationInvitation.organization_id == current.org_id,
        )
    )
    if inv is None:
        raise NotFoundError("Invitation not found")
    db.delete(inv)
    audit.record(
        db,
        org_id=current.org_id,
        user_id=current.id,
        action="member.invitation_revoked",
        resource_type="invitation",
        resource_id=invitation_id,
        ip_address=client_ip(request),
    )
    return Message(message="Invitation revoked")


@router.get("/audit-logs", response_model=Page[AuditLogOut])
def audit_logs(
    current: Auditor,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: str | None = Query(None, max_length=64),
    user_id: uuid.UUID | None = None,
) -> Page[AuditLogOut]:
    stmt = (
        select(AuditLog, User.email)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(AuditLog.organization_id == current.org_id)
    )
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action))
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = []
    for log, email in rows:
        out = AuditLogOut.model_validate(log)
        out.user_email = email
        items.append(out)
    return Page(items=items, total=total, page=page, page_size=page_size)
