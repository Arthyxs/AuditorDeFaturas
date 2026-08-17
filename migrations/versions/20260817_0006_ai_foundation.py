"""Add versioned AI pricing and immutable call telemetry.

Revision ID: 20260817_0006
Revises: 20260817_0005
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0006"
down_revision: str | None = "20260817_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_price_versions",
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_per_million", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("cached_input_per_million", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("output_per_million", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name=op.f("ck_ai_price_versions_valid_effective_window"),
        ),
        sa.CheckConstraint(
            "input_per_million >= 0 AND cached_input_per_million >= 0 AND output_per_million >= 0",
            name=op.f("ck_ai_price_versions_nonnegative_prices"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_price_versions")),
        sa.UniqueConstraint(
            "provider",
            "model",
            "version",
            name=op.f("uq_ai_price_versions_provider_model_version"),
        ),
    )
    op.create_index(
        "ix_ai_price_versions_effective",
        "ai_price_versions",
        ["provider", "model", "effective_from"],
    )
    op.create_table(
        "ai_calls",
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("task", sa.String(length=64), nullable=False),
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("prompt_name", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("tool_rounds", sa.Integer(), nullable=False),
        sa.Column("tool_calls", sa.Integer(), nullable=False),
        sa.Column("price_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("audit_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("duration_ms >= 0", name=op.f("ck_ai_calls_nonnegative_duration")),
        sa.CheckConstraint(
            "input_tokens >= 0 AND cached_input_tokens >= 0 AND output_tokens >= 0",
            name=op.f("ck_ai_calls_nonnegative_tokens"),
        ),
        sa.CheckConstraint(
            "cached_input_tokens <= input_tokens",
            name=op.f("ck_ai_calls_cached_within_input"),
        ),
        sa.CheckConstraint(
            "status IN ('SUCCEEDED', 'ERROR')", name=op.f("ck_ai_calls_ai_call_status")
        ),
        sa.CheckConstraint(
            "tool_rounds >= 0 AND tool_calls >= 0",
            name=op.f("ck_ai_calls_nonnegative_tool_counts"),
        ),
        sa.ForeignKeyConstraint(
            ["price_version_id"],
            ["ai_price_versions.id"],
            name=op.f("fk_ai_calls_price_version_id_ai_price_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_calls")),
    )
    op.create_index("ix_ai_calls_audit_run_id", "ai_calls", ["audit_run_id"])
    op.create_index(
        "ix_ai_calls_provider_model_started", "ai_calls", ["provider", "model", "started_at"]
    )
    op.create_index("ix_ai_calls_task_started", "ai_calls", ["task", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_calls_task_started", table_name="ai_calls")
    op.drop_index("ix_ai_calls_provider_model_started", table_name="ai_calls")
    op.drop_index("ix_ai_calls_audit_run_id", table_name="ai_calls")
    op.drop_table("ai_calls")
    op.drop_index("ix_ai_price_versions_effective", table_name="ai_price_versions")
    op.drop_table("ai_price_versions")
