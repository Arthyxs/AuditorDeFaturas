"""Authentication, bootstrap and session routes."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from app.api.dependencies import (
    SESSION_COOKIE_NAME,
    CurrentUser,
    get_auth_service,
    verify_same_origin,
)
from app.api.schemas.auth import (
    BootstrapRequest,
    BootstrapStatusResponse,
    LoginRequest,
    LogoutResponse,
    UserResponse,
)
from app.application.services.auth import (
    AuthenticationError,
    AuthService,
    BootstrapUnavailableError,
)
from app.config import Settings
from app.infrastructure.persistence.models import UserRole

router = APIRouter(prefix="/api/auth", tags=["authentication"])


def _user_response(username: str, role: UserRole) -> UserResponse:
    return UserResponse(username=username, role=role)


def _set_session_cookie(response: Response, request: Request, token: str, max_age: int) -> None:
    settings: Settings = request.app.state.settings
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.app_base_url.scheme == "https",
        samesite="strict",
        path="/",
    )


@router.get("/bootstrap/status", response_model=BootstrapStatusResponse)
def bootstrap_status(
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> BootstrapStatusResponse:
    """Tell the frontend whether first access still needs initialization."""
    return BootstrapStatusResponse(available=service.bootstrap_available())


@router.post(
    "/bootstrap",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_same_origin)],
)
def bootstrap(
    payload: BootstrapRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserResponse:
    """Create and authenticate the first administrator exactly once."""
    try:
        user = service.create_first_admin(
            payload.username, payload.password, payload.bootstrap_token
        )
        authenticated = service.create_session(user)
    except (BootstrapUnavailableError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="bootstrap unavailable"
        ) from exc
    _set_session_cookie(
        response,
        request,
        authenticated.token,
        request.app.state.settings.session_lifetime_minutes * 60,
    )
    return _user_response(user.username, user.role)


@router.post("/login", response_model=UserResponse, dependencies=[Depends(verify_same_origin)])
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserResponse:
    """Create a revocable server-side session for valid credentials."""
    try:
        user = service.authenticate(payload.username, payload.password)
    except (AuthenticationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        ) from exc
    authenticated = service.create_session(user)
    _set_session_cookie(
        response,
        request,
        authenticated.token,
        request.app.state.settings.session_lifetime_minutes * 60,
    )
    return _user_response(user.username, user.role)


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    """Return the authenticated identity and effective role."""
    return _user_response(user.username, user.role)


@router.post("/logout", response_model=LogoutResponse, dependencies=[Depends(verify_same_origin)])
def logout(
    response: Response,
    user: CurrentUser,
    service: Annotated[AuthService, Depends(get_auth_service)],
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> LogoutResponse:
    """Revoke the current server-side session and expire its cookie."""
    del user
    if token is not None:
        service.revoke_session(token)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/", httponly=True, samesite="strict")
    return LogoutResponse(logged_out=True)
