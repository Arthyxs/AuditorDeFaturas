"""Add M14 canonical invoice intake and invoice aggregate.

Revision ID: 20260817_0008
Revises: 20260817_0007
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0008"
down_revision: str | None = "20260817_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
MONEY = sa.Numeric(20, 6)


def _id_created() -> list[sa.Column]:
    return [
        sa.Column("id", UUID, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "partners",
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("document_id", sa.String(64), nullable=True),
        sa.Column(
            "aliases", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        *_id_created(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partners")),
        sa.UniqueConstraint("document_id", name=op.f("uq_partners_document_id")),
        sa.UniqueConstraint("normalized_name", name=op.f("uq_partners_normalized_name")),
    )
    op.create_table(
        "invoice_submissions",
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("mail_message_id", UUID, nullable=True),
        sa.Column("submitted_by_id", UUID, nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        *_id_created(),
        sa.CheckConstraint(
            "source_type IN ('IMAP', 'MANUAL')",
            name=op.f("ck_invoice_submissions_submission_source"),
        ),
        sa.CheckConstraint(
            "(source_type = 'IMAP' AND mail_message_id IS NOT NULL AND submitted_by_id IS NULL) OR "
            "(source_type = 'MANUAL' AND mail_message_id IS NULL AND submitted_by_id IS NOT NULL)",
            name=op.f("ck_invoice_submissions_submission_origin_reference"),
        ),
        sa.CheckConstraint(
            "status IN ('ACCEPTED')", name=op.f("ck_invoice_submissions_submission_status")
        ),
        sa.ForeignKeyConstraint(
            ["mail_message_id"],
            ["mail_messages.id"],
            name=op.f("fk_invoice_submissions_mail_message_id_mail_messages"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_id"],
            ["users.id"],
            name=op.f("fk_invoice_submissions_submitted_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_submissions")),
        sa.UniqueConstraint("content_hash", name=op.f("uq_invoice_submissions_content_hash")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_invoice_submissions_idempotency_key")),
        sa.UniqueConstraint("mail_message_id", name=op.f("uq_invoice_submissions_mail_message_id")),
    )
    op.create_table(
        "submission_files",
        sa.Column("submission_id", UUID, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(255), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        *_id_created(),
        sa.CheckConstraint(
            "role IN ('INVOICE', 'AUXILIARY')",
            name=op.f("ck_submission_files_submission_file_role"),
        ),
        sa.CheckConstraint(
            "ordinal >= 0", name=op.f("ck_submission_files_submission_file_ordinal")
        ),
        sa.CheckConstraint("size >= 0", name=op.f("ck_submission_files_submission_file_size")),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["invoice_submissions.id"],
            name=op.f("fk_submission_files_submission_id_invoice_submissions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submission_files")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_submission_files_storage_key")),
        sa.UniqueConstraint("submission_id", "ordinal", name=op.f("uq_submission_files_ordinal")),
    )
    op.create_table(
        "invoices",
        sa.Column("submission_id", UUID, nullable=False),
        sa.Column("mail_message_id", UUID, nullable=True),
        sa.Column("partner_id", UUID, nullable=True),
        sa.Column("partner_name_raw", sa.String(255), nullable=True),
        sa.Column("invoice_number", sa.String(255), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("amount_charged", MONEY, nullable=True),
        sa.Column("amount_expected", MONEY, nullable=True),
        sa.Column("difference", MONEY, nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        *_id_created(),
        sa.CheckConstraint(
            "status IN ('PROCESSING', 'CORRECT', 'INCORRECT', 'PENDING', "
            "'MANUAL_REVIEW', 'NOT_AUDITABLE', 'ERROR')",
            name=op.f("ck_invoices_invoice_status"),
        ),
        sa.ForeignKeyConstraint(
            ["mail_message_id"],
            ["mail_messages.id"],
            name=op.f("fk_invoices_mail_message_id_mail_messages"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["partners.id"],
            name=op.f("fk_invoices_partner_id_partners"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["invoice_submissions.id"],
            name=op.f("fk_invoices_submission_id_invoice_submissions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoices")),
        sa.UniqueConstraint("submission_id", name=op.f("uq_invoices_submission_id")),
    )
    op.create_index("ix_invoices_status_created", "invoices", ["status", "created_at"])
    op.create_table(
        "invoice_documents",
        sa.Column("invoice_id", UUID, nullable=False),
        sa.Column("document_type", sa.String(64)),
        sa.Column("document_number", sa.String(255)),
        sa.Column("issue_date", sa.Date()),
        sa.Column("origin_city", sa.String(255)),
        sa.Column("origin_state", sa.String(64)),
        sa.Column("destination_city", sa.String(255)),
        sa.Column("destination_state", sa.String(64)),
        sa.Column("origin_zip", sa.String(32)),
        sa.Column("destination_zip", sa.String(32)),
        sa.Column("real_weight", MONEY),
        sa.Column("cubic_weight", MONEY),
        sa.Column("chargeable_weight", MONEY),
        sa.Column("merchandise_value", MONEY),
        sa.Column("amount_charged", MONEY),
        sa.Column("amount_expected", MONEY),
        sa.Column("difference", MONEY),
        sa.Column("our_freight_revenue", MONEY),
        sa.Column("gross_margin_actual", MONEY),
        sa.Column("gross_margin_expected", MONEY),
        sa.Column("status", sa.String(32)),
        sa.Column(
            "source_reference",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        *_id_created(),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            name=op.f("fk_invoice_documents_invoice_id_invoices"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_documents")),
    )
    op.create_index(
        "ix_invoice_documents_invoice_number",
        "invoice_documents",
        ["invoice_id", "document_number"],
    )
    op.create_table(
        "document_charge_items",
        sa.Column("invoice_document_id", UUID, nullable=False),
        sa.Column("name_raw", sa.String(255), nullable=False),
        sa.Column("name_normalized", sa.String(255)),
        sa.Column("charged_amount", MONEY),
        sa.Column("expected_amount", MONEY),
        sa.Column("difference", MONEY),
        sa.Column("status", sa.String(32)),
        sa.Column(
            "evidence", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        *_id_created(),
        sa.ForeignKeyConstraint(
            ["invoice_document_id"],
            ["invoice_documents.id"],
            name=op.f("fk_document_charge_items_invoice_document_id_invoice_documents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_charge_items")),
    )


def downgrade() -> None:
    op.drop_table("document_charge_items")
    op.drop_index("ix_invoice_documents_invoice_number", table_name="invoice_documents")
    op.drop_table("invoice_documents")
    op.drop_index("ix_invoices_status_created", table_name="invoices")
    op.drop_table("invoices")
    op.drop_table("submission_files")
    op.drop_table("invoice_submissions")
    op.drop_table("partners")
