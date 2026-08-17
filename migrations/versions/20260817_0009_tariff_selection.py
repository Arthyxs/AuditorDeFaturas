"""Add M15 semantic tariff selection and pending items.

Revision ID: 20260817_0009
Revises: 20260817_0008
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0009"
down_revision: str | None = "20260817_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tariff_selection_runs",
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("threshold", sa.Numeric(5, 4), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ai_call_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('SELECTED', 'NO_TARIFF', 'LOW_CONFIDENCE')",
            name=op.f("ck_tariff_selection_runs_tariff_selection_status"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("ck_tariff_selection_runs_tariff_selection_confidence"),
        ),
        sa.CheckConstraint(
            "threshold >= 0 AND threshold <= 1",
            name=op.f("ck_tariff_selection_runs_tariff_selection_threshold"),
        ),
        sa.ForeignKeyConstraint(
            ["ai_call_id"],
            ["ai_calls.id"],
            name=op.f("fk_tariff_selection_runs_ai_call_id_ai_calls"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            name=op.f("fk_tariff_selection_runs_invoice_id_invoices"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tariff_selection_runs")),
        sa.UniqueConstraint("invoice_id", name=op.f("uq_tariff_selection_runs_invoice_id")),
    )
    op.create_table(
        "tariff_selection_files",
        sa.Column("selection_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tariff_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["selection_run_id"],
            ["tariff_selection_runs.id"],
            name=op.f("fk_tariff_selection_files_selection_run_id_tariff_selection_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tariff_file_id"],
            ["tariff_files.id"],
            name=op.f("fk_tariff_selection_files_tariff_file_id_tariff_files"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tariff_selection_files")),
        sa.UniqueConstraint(
            "selection_run_id", "tariff_file_id", name=op.f("uq_selection_tariff_file")
        ),
    )
    op.create_table(
        "pending_items",
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("audit_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "required_information",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'RESOLVED', 'DISMISSED')",
            name=op.f("ck_pending_items_pending_status"),
        ),
        sa.ForeignKeyConstraint(
            ["invoice_document_id"],
            ["invoice_documents.id"],
            name=op.f("fk_pending_items_invoice_document_id_invoice_documents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            name=op.f("fk_pending_items_invoice_id_invoices"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pending_items")),
        sa.UniqueConstraint("invoice_id", "type", name=op.f("uq_pending_items_invoice_type")),
    )


def downgrade() -> None:
    op.drop_table("pending_items")
    op.drop_table("tariff_selection_files")
    op.drop_table("tariff_selection_runs")
