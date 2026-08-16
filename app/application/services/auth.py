"""Authentication and first-administrator application service."""

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session, joinedload

from app.config import Settings
from app.infrastructure.persistence.models import AuthSession, User, UserRole
from app.infrastructure.security.passwords import hash_password, verify_password
from app.infrastructure.security.sessions import hash_session_token, new_session_token

_BOOTSTRAP_ADVISORY_LOCK = 4_942_456_505
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-account-password")


class BootstrapUnavailableError(Exception):
    """The first-administrator flow is closed or the token is invalid."""


class AuthenticationError(Exception):
    """Credentials or session are invalid."""


@dataclass(frozen=True)
class AuthenticatedSession:
    """New session data split between database record and client cookie."""

    token: str
    expires_at: datetime


class AuthService:
    """Coordinate user credentials and revocable server-side sessions."""

    def __init__(self, database: Session, settings: Settings) -> None:
        self._database = database
        self._settings = settings

    def bootstrap_available(self) -> bool:
        """Return whether the one-time bootstrap endpoint is still open."""
        return not self._database.scalar(
            select(User.id).where(User.role == UserRole.ADMIN).limit(1)
        )

    def create_first_admin(self, username: str, password: str, token: str) -> User:
        """Atomically create the only administrator allowed through bootstrap."""
        self._database.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": _BOOTSTRAP_ADVISORY_LOCK}
        )
        if not self.bootstrap_available() or not hmac.compare_digest(
            token, self._settings.first_admin_bootstrap_token.get_secret_value()
        ):
            raise BootstrapUnavailableError

        user = User(
            username=normalize_username(username),
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        self._database.add(user)
        self._database.flush()
        return user

    def authenticate(self, username: str, password: str) -> User:
        """Verify active user credentials with a generic failure result."""
        normalized = normalize_username(username)
        user = self._database.scalar(select(User).where(User.username == normalized))
        candidate_hash = _DUMMY_PASSWORD_HASH if user is None else user.password_hash
        password_matches = verify_password(candidate_hash, password)
        if user is None or not user.is_active or not password_matches:
            raise AuthenticationError
        return user

    def create_session(self, user: User, *, now: datetime | None = None) -> AuthenticatedSession:
        """Persist only a digest of a newly generated opaque session token."""
        current = datetime.now(UTC) if now is None else now
        expires_at = current + timedelta(minutes=self._settings.session_lifetime_minutes)
        token = new_session_token()
        self._database.add(
            AuthSession(
                token_hash=hash_session_token(token),
                user_id=user.id,
                expires_at=expires_at,
            )
        )
        self._database.flush()
        return AuthenticatedSession(token=token, expires_at=expires_at)

    def resolve_session(self, token: str, *, now: datetime | None = None) -> User:
        """Resolve an unexpired, unrevoked session and active user."""
        current = datetime.now(UTC) if now is None else now
        record = self._database.scalar(
            select(AuthSession)
            .options(joinedload(AuthSession.user))
            .where(AuthSession.token_hash == hash_session_token(token))
        )
        if (
            record is None
            or record.revoked_at is not None
            or record.expires_at <= current
            or not record.user.is_active
        ):
            raise AuthenticationError
        return record.user

    def revoke_session(self, token: str, *, now: datetime | None = None) -> None:
        """Revoke a session idempotently without exposing whether it existed."""
        record = self._database.scalar(
            select(AuthSession).where(AuthSession.token_hash == hash_session_token(token))
        )
        if record is not None and record.revoked_at is None:
            record.revoked_at = datetime.now(UTC) if now is None else now


def normalize_username(username: str) -> str:
    """Normalize and validate a local login identifier."""
    normalized = username.strip().casefold()
    if len(normalized) < 3 or len(normalized) > 255 or any(char.isspace() for char in normalized):
        raise ValueError("username must contain 3-255 non-whitespace characters")
    return normalized
