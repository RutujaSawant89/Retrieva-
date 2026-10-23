from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=128)
    # Either create a new organization, or join one through an invitation token.
    organization_name: str | None = Field(default=None, min_length=2, max_length=200)
    invitation_token: str | None = Field(default=None, max_length=128)

    @field_validator("full_name", "organization_name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    organization_id: uuid.UUID | None = None


class SwitchOrganizationRequest(BaseModel):
    organization_id: uuid.UUID


class OrganizationSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: str


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    created_at: datetime
    last_login_at: datetime | None = None


class SessionOut(BaseModel):
    """Returned by login/register/refresh. The refresh token travels only in an httpOnly cookie."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_at: datetime
    user: UserOut
    organization: OrganizationSummary
    organizations: list[OrganizationSummary]
    permissions: list[str]


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)
