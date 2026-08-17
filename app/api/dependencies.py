"""FastAPI dependencies for database-backed authentication and RBAC."""

from collections.abc import Callable, Iterator
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.application.services.auth import AuthenticationError, AuthService
from app.config import Settings
from app.infrastructure.persistence.models import User, UserRole
from app.ports.storage import StorageProvider

SESSION_COOKIE_NAME = "invoice_auditor_session"


def get_database(request: Request) -> Iterator[Session]:
    """Provide one transaction per request."""
    database = request.app.state.session_factory()
    try:
        yield database
        database.commit()
    except BaseException:
        database.rollback()
        raise
    finally:
        database.close()


def get_auth_service(
    request: Request, database: Annotated[Session, Depends(get_database)]
) -> AuthService:
    """Bind authentication to the request database transaction and settings."""
    settings: Settings = request.app.state.settings
    return AuthService(database, settings)


def get_storage(request: Request) -> StorageProvider:
    """Expose the configured storage implementation through its replaceable port."""
    storage: StorageProvider = request.app.state.storage_provider
    return storage


def verify_same_origin(request: Request) -> None:
    """Reject cross-site or origin-less unsafe browser requests."""
    origin = request.headers.get("origin")
    settings: Settings = request.app.state.settings
    configured = urlsplit(str(settings.app_base_url))
    expected = f"{configured.scheme}://{configured.netloc}"
    if origin is None or origin.rstrip("/") != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid request origin")


def get_current_user(
    service: Annotated[AuthService, Depends(get_auth_service)],
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> User:
    """Resolve the current server-side session from its opaque cookie."""
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    try:
        return service.resolve_session(token)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        ) from exc


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*allowed: UserRole) -> Callable[[CurrentUser], User]:
    """Create a reusable route authorization dependency."""

    def authorize(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return user

    return authorize
