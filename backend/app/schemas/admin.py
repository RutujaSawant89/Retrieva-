from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel

RoleLiteral = Literal["admin", "analyst", "researcher", "viewer"]


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    joined_at: datetime
    last_login_at: datetime | None


class MemberRoleUpdate(BaseModel):
    role: RoleLiteral


class InvitationCreate(BaseModel):
    email: EmailStr
    role: RoleLiteral = "viewer"


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime
    # Only present in the creation response; it is never stored in plain text.
    token: str | None = None


class AuditLogOut(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    user_email: str | None = None
    action: str
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    correlation_id: str | None
    details: dict
    created_at: datetime


class OrganizationOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class RoleOut(BaseModel):
    name: str
    description: str
    permissions: list[str]
