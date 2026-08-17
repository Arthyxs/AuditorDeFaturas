"""PostgreSQL durable-job persistence model."""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.jobs import JobStatus
from app.infrastructure.persistence.models.base import (
    Base,
    CreatedAtMixin,
    UpdatedAtMixin,
    UUIDPrimaryKeyMixin,
)
from app.infrastructure.persistence.types import string_enum_type


class ProcessingJob(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """One idempotent unit of background work with a renewable lease."""

    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        CheckConstraint("attempts <= max_attempts", name="attempts_within_limit"),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'RETRY_SCHEDULED', 'SUCCEEDED', 'FAILED')",
            name="processing_job_status",
        ),
        Index(
            "ix_processing_jobs_claim",
            "status",
            "available_at",
            "priority",
            "created_at",
        ),
        Index("ix_processing_jobs_stale", "status", "heartbeat_at"),
    )

    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
    status: Mapped[JobStatus] = mapped_column(
        string_enum_type(JobStatus, name="processing_job_status", create_constraint=False),
        nullable=False,
        default=JobStatus.PENDING,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
