"""Versioned AI pricing and immutable logical-call telemetry."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.persistence.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class AIPriceVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "ai_price_versions"
    __table_args__ = (
        UniqueConstraint(
            "provider", "model", "version", name="uq_ai_price_versions_provider_model_version"
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="valid_effective_window",
        ),
        CheckConstraint(
            "input_per_million >= 0 AND cached_input_per_million >= 0 AND output_per_million >= 0",
            name="nonnegative_prices",
        ),
        Index("ix_ai_price_versions_effective", "provider", "model", "effective_from"),
    )

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_per_million: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    cached_input_per_million: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    output_per_million: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    calls: Mapped[list["AICall"]] = relationship(back_populates="price_version")


class AICall(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "ai_calls"
    __table_args__ = (
        CheckConstraint("duration_ms >= 0", name="nonnegative_duration"),
        CheckConstraint(
            "input_tokens >= 0 AND cached_input_tokens >= 0 AND output_tokens >= 0",
            name="nonnegative_tokens",
        ),
        CheckConstraint("cached_input_tokens <= input_tokens", name="cached_within_input"),
        CheckConstraint("status IN ('SUCCEEDED', 'ERROR')", name="ai_call_status"),
        CheckConstraint("tool_rounds >= 0 AND tool_calls >= 0", name="nonnegative_tool_counts"),
        Index("ix_ai_calls_provider_model_started", "provider", "model", "started_at"),
        Index("ix_ai_calls_task_started", "task", "started_at"),
    )

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    task: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_name: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    price_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ai_price_versions.id", ondelete="RESTRICT"), nullable=True
    )
    audit_run_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True, index=True
    )

    price_version: Mapped[AIPriceVersion | None] = relationship(back_populates="calls")
