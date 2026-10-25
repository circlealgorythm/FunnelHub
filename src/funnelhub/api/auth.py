from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from funnelhub.config import Settings, get_settings
from funnelhub.services.auth import (
    SESSION_COOKIE_NAME,
    AuthenticatedAdmin,
    authenticate_admin,
    create_session_cookie,
    is_auth_configured,
    require_admin_session,
    revoke_session,
    safe_auth_status,
    should_use_secure_cookie,
)
from funnelhub.services.ingestion_guard import enforce_login_rate_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
AdminDep = Annotated[AuthenticatedAdmin, Depends(require_admin_session)]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class AuthStatusResponse(BaseModel):
    authenticated: bool
    username: str | None = None
    configured: bool = True


@router.post("/login", response_model=AuthStatusResponse)
async def login(
    http_request: Request,
    request: LoginRequest,
    response: Response,
    settings: SettingsDep,
) -> AuthStatusResponse:
    enforce_login_rate_limit(request=http_request, settings=settings)
    if not is_auth_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Inbox authentication is not configured.",
        )

    if not authenticate_admin(settings, request.username, request.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    cookie_value = create_session_cookie(settings, request.username.strip())
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=settings.inbox_session_ttl_seconds,
        httponly=True,
        secure=should_use_secure_cookie(settings),
        samesite="lax",
        path="/",
    )
    return AuthStatusResponse(authenticated=True, username=request.username.strip())


@router.get("/me", response_model=AuthStatusResponse)
async def me(
    admin: AdminDep,
    settings: SettingsDep,
) -> AuthStatusResponse:
    auth_status = safe_auth_status(settings)
    return AuthStatusResponse(
        authenticated=True,
        username=admin.username,
        configured=bool(auth_status["configured"]),
    )


@router.post("/logout", response_model=AuthStatusResponse)
async def logout(
    response: Response,
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> AuthStatusResponse:
    if session_cookie:
        revoke_session(session_cookie)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return AuthStatusResponse(authenticated=False)
