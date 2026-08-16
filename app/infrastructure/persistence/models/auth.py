"""Authentication persistence models."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.persistence.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.infrastructure.persistence.types import PersistedEnum, string_enum_type


class UserRole(PersistedEnum):
    """Application authorization roles."""

    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"


class User(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Local authenticated user."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('ADMIN', 'OPERATOR', 'VIEWER')", name="user_role"),)

    username: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        string_enum_type(UserRole, name="user_role", create_constraint=False), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user")


class AuthSession(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Revocable server-side session identified by a hashed opaque token."""

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user: Mapped[User] = relationship(back_populates="sessions")


class AuthorizationRole(StrEnum):
    """Public role names accepted by authorization helpers."""

    ADMIN = UserRole.ADMIN.value
    OPERATOR = UserRole.OPERATOR.value
    VIEWER = UserRole.VIEWER.value
