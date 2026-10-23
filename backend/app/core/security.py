"""Password hashing, password policy, JWT access tokens and opaque refresh tokens."""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()  # Argon2id with library defaults (memory-hard)

# Used to equalise timing when a login targets an unknown email address.
_DUMMY_HASH = _hasher.hash("retrieva-timing-equaliser")

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128
_COMMON_PASSWORDS = {
    "password",
    "password1",
    "password123",
    "123456789",
    "1234567890",
    "qwerty123",
    "letmein123",
    "welcome123",
    "admin12345",
    "iloveyou12",
}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def validate_password_strength(password: str, *, email: str | None = None) -> list[str]:
    """Return a list of policy violations (empty when the password is acceptable)."""
    problems: list[str] = []
    if len(password) < PASSWORD_MIN_LENGTH:
        problems.append(f"must be at least {PASSWORD_MIN_LENGTH} characters")
    if len(password) > PASSWORD_MAX_LENGTH:
        problems.append(f"must be at most {PASSWORD_MAX_LENGTH} characters")
    classes = sum(
        bool(re.search(pattern, password)) for pattern in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]")
    )
    if classes < 3:
        problems.append("must contain at least three of: lowercase, uppercase, digit, symbol")
    if password.lower() in _COMMON_PASSWORDS:
        problems.append("is too common")
    if email:
        local = email.split("@", 1)[0].lower()
        if len(local) >= 4 and local in password.lower():
            problems.append("must not contain your email name")
    return problems


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    org_id: uuid.UUID
    role: str
    jti: str
    expires_at: datetime


class TokenError(Exception):
    pass


def create_access_token(user_id: uuid.UUID, org_id: uuid.UUID, role: str) -> tuple[str, datetime]:
    settings = get_settings()
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "org": str(org_id),
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": secrets.token_hex(8),
        "iss": "retrieva",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires


def decode_access_token(token: str) -> AccessTokenClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer="retrieva",
            options={"require": ["sub", "org", "exp", "iat", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError("invalid or expired token") from exc
    if payload.get("type") != "access":
        raise TokenError("wrong token type")
    try:
        return AccessTokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            org_id=uuid.UUID(payload["org"]),
            role=str(payload.get("role", "")),
            jti=str(payload.get("jti", "")),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
        )
    except (ValueError, KeyError) as exc:
        raise TokenError("malformed token") from exc


def new_opaque_token() -> str:
    """URL-safe random token for refresh tokens and invitations (~256 bits)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
