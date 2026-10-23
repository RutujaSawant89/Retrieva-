from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.deps import AuthUser, DbSession, client_ip
from app.core.config import get_settings
from app.core.rate_limit import rate_limiter
from app.schemas.auth import (
    LoginRequest,
    PasswordChange,
    ProfileUpdate,
    RegisterRequest,
    SessionOut,
    SwitchOrganizationRequest,
    UserOut,
)
from app.schemas.common import Message
from app.services import audit, auth_service
from app.services.auth_service import ClientInfo, IssuedSession

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_PATH = "/api/v1/auth"


def _client(request: Request) -> ClientInfo:
    return ClientInfo(ip=client_ip(request), user_agent=request.headers.get("user-agent"))


def _set_refresh_cookie(response: Response, issued: IssuedSession) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.refresh_cookie_name,
        issued.refresh_token,
        expires=issued.refresh_expires_at,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=REFRESH_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


def _limit_auth(request: Request, bucket: str) -> None:
    rate_limiter.hit(f"auth:{bucket}:{client_ip(request)}", get_settings().auth_rate_limit_per_minute)


@router.post("/register", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request, response: Response, db: DbSession) -> SessionOut:
    _limit_auth(request, "register")
    issued = auth_service.register(
        db,
        email=body.email,
        full_name=body.full_name,
        password=body.password,
        organization_name=body.organization_name,
        invitation_token=body.invitation_token,
        client=_client(request),
    )
    _set_refresh_cookie(response, issued)
    return issued.body


@router.post("/login", response_model=SessionOut)
def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> SessionOut:
    _limit_auth(request, "login")
    issued = auth_service.login(
        db,
        email=body.email,
        password=body.password,
        organization_id=body.organization_id,
        client=_client(request),
    )
    _set_refresh_cookie(response, issued)
    return issued.body


@router.post("/refresh", response_model=SessionOut)
def refresh(request: Request, response: Response, db: DbSession) -> SessionOut:
    _limit_auth(request, "refresh")
    raw = request.cookies.get(get_settings().refresh_cookie_name)
    issued = auth_service.refresh(db, raw, _client(request))
    _set_refresh_cookie(response, issued)
    return issued.body


@router.post("/switch-organization", response_model=SessionOut)
def switch_organization(
    body: SwitchOrganizationRequest, request: Request, response: Response, db: DbSession
) -> SessionOut:
    raw = request.cookies.get(get_settings().refresh_cookie_name)
    issued = auth_service.refresh(db, raw, _client(request), org_id=body.organization_id)
    _set_refresh_cookie(response, issued)
    return issued.body


@router.post("/logout", response_model=Message)
def logout(request: Request, response: Response, db: DbSession) -> Message:
    auth_service.logout(db, request.cookies.get(get_settings().refresh_cookie_name))
    _clear_refresh_cookie(response)
    return Message(message="Signed out")


@router.get("/me", response_model=UserOut)
def me(current: AuthUser) -> UserOut:
    return UserOut.model_validate(current.user)


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, current: AuthUser, request: Request, db: DbSession) -> UserOut:
    user = db.merge(current.user)
    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    audit.record(
        db,
        org_id=current.org_id,
        user_id=user.id,
        action="user.profile_updated",
        ip_address=client_ip(request),
    )
    db.flush()
    return UserOut.model_validate(user)


@router.post("/me/password", response_model=Message)
def change_password(
    body: PasswordChange, current: AuthUser, request: Request, response: Response, db: DbSession
) -> Message:
    _limit_auth(request, "password")
    auth_service.change_password(
        db, db.merge(current.user), current.org_id, body.current_password, body.new_password
    )
    _clear_refresh_cookie(response)
    return Message(message="Password changed. Please sign in again.")
