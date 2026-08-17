"""Add M13 e-mail classification and movement lifecycle.

Revision ID: 20260817_0007
Revises: 20260817_0006
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0007"
down_revision: str | None = "20260817_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_mail_messages_mail_message_status"), "mail_messages", type_="check")
    op.add_column("mail_messages", sa.Column("classification", sa.String(32), nullable=True))
    op.add_column(
        "mail_messages", sa.Column("classification_confidence", sa.Numeric(5, 4), nullable=True)
    )
    op.add_column(
        "mail_messages", sa.Column("classification_threshold", sa.Numeric(5, 4), nullable=True)
    )
    op.add_column("mail_messages", sa.Column("partner_name", sa.String(255), nullable=True))
    op.add_column("mail_messages", sa.Column("partner_document_id", sa.String(64), nullable=True))
    op.add_column(
        "mail_messages",
        sa.Column(
            "invoice_attachment_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "mail_messages",
        sa.Column(
            "supporting_attachment_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("mail_messages", sa.Column("classification_summary", sa.Text(), nullable=True))
    op.add_column(
        "mail_messages",
        sa.Column(
            "classification_evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "mail_messages",
        sa.Column("classification_ai_call_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("mail_messages", sa.Column("classified_at", sa.DateTime(timezone=True)))
    op.add_column("mail_messages", sa.Column("moved_at", sa.DateTime(timezone=True)))
    op.add_column("mail_messages", sa.Column("processing_error_code", sa.String(64)))
    op.add_column("mail_messages", sa.Column("processing_error_detail", sa.Text()))
    op.add_column(
        "mail_messages", sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("mail_messages", sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column("mail_messages", sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        op.f("fk_mail_messages_classification_ai_call_id_ai_calls"),
        "mail_messages",
        "ai_calls",
        ["classification_ai_call_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_mail_messages_reviewed_by_id_users"),
        "mail_messages",
        "users",
        ["reviewed_by_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "mail_message_status",
        "mail_messages",
        "status IN ('INGESTED', 'CLASSIFIED', 'MOVED', 'MANUAL_REVIEW', 'ERROR')",
    )
    op.create_check_constraint(
        "mail_message_classification",
        "mail_messages",
        "classification IS NULL OR classification IN "
        "('INVOICE', 'DUE_NOTICE', 'GENERAL', 'MANUAL_REVIEW')",
    )
    op.create_check_constraint(
        "classification_confidence_range",
        "mail_messages",
        "classification_confidence IS NULL OR "
        "(classification_confidence >= 0 AND classification_confidence <= 1)",
    )
    op.create_check_constraint(
        "classification_threshold_range",
        "mail_messages",
        "classification_threshold IS NULL OR "
        "(classification_threshold >= 0 AND classification_threshold <= 1)",
    )
    op.create_index("ix_mail_messages_manual_review", "mail_messages", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_mail_messages_manual_review", table_name="mail_messages")
    op.drop_constraint(
        op.f("ck_mail_messages_classification_threshold_range"),
        "mail_messages",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_mail_messages_classification_confidence_range"),
        "mail_messages",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_mail_messages_mail_message_classification"),
        "mail_messages",
        type_="check",
    )
    op.drop_constraint(op.f("ck_mail_messages_mail_message_status"), "mail_messages", type_="check")
    op.create_check_constraint("mail_message_status", "mail_messages", "status IN ('INGESTED')")
    op.drop_constraint(
        op.f("fk_mail_messages_reviewed_by_id_users"), "mail_messages", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_mail_messages_classification_ai_call_id_ai_calls"),
        "mail_messages",
        type_="foreignkey",
    )
    for column in (
        "reviewed_at",
        "review_note",
        "reviewed_by_id",
        "processing_error_detail",
        "processing_error_code",
        "moved_at",
        "classified_at",
        "classification_ai_call_id",
        "classification_evidence",
        "classification_summary",
        "supporting_attachment_ids",
        "invoice_attachment_ids",
        "partner_document_id",
        "partner_name",
        "classification_threshold",
        "classification_confidence",
        "classification",
    ):
        op.drop_column("mail_messages", column)
