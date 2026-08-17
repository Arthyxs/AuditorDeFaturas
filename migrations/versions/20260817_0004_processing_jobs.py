"""Add durable PostgreSQL processing jobs.

Revision ID: 20260817_0004
Revises: 20260817_0003
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0004"
down_revision: str | None = "20260817_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the durable queue and its claim/recovery indexes."""
    op.create_table(
        "processing_jobs",
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=15), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_by", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_processing_jobs_attempts_nonnegative")),
        sa.CheckConstraint(
            "max_attempts >= 1", name=op.f("ck_processing_jobs_max_attempts_positive")
        ),
        sa.CheckConstraint(
            "attempts <= max_attempts", name=op.f("ck_processing_jobs_attempts_within_limit")
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'RETRY_SCHEDULED', 'SUCCEEDED', 'FAILED')",
            name=op.f("ck_processing_jobs_processing_job_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_jobs")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_processing_jobs_idempotency_key")),
    )
    op.create_index(
        "ix_processing_jobs_claim",
        "processing_jobs",
        ["status", "available_at", "priority", "created_at"],
    )
    op.create_index("ix_processing_jobs_stale", "processing_jobs", ["status", "heartbeat_at"])


def downgrade() -> None:
    """Remove the durable queue."""
    op.drop_index("ix_processing_jobs_stale", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_claim", table_name="processing_jobs")
    op.drop_table("processing_jobs")
