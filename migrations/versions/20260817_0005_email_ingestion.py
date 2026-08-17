"""Add canonical e-mail originals and deduplication identities.

Revision ID: 20260817_0005
Revises: 20260817_0004
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0005"
down_revision: str | None = "20260817_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mail_accounts",
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("ssl", sa.Boolean(), nullable=False),
        sa.Column("username", sa.String(length=320), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint("port >= 1 AND port <= 65535", name=op.f("ck_mail_accounts_valid_port")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mail_accounts")),
        sa.UniqueConstraint(
            "host", "port", "username", name=op.f("uq_mail_accounts_mailbox_identity")
        ),
    )
    op.create_table(
        "mail_messages",
        sa.Column("mail_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uidvalidity", sa.BigInteger(), nullable=False),
        sa.Column("uid", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.String(length=998), nullable=True),
        sa.Column("in_reply_to", sa.String(length=998), nullable=True),
        sa.Column("references", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("normalized_subject", sa.Text(), nullable=False),
        sa.Column("sender", sa.String(length=998), nullable=False),
        sa.Column("normalized_sender", sa.String(length=998), nullable=False),
        sa.Column("recipients", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("header_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("normalized_body_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_size", sa.BigInteger(), nullable=False),
        sa.Column("raw_sha256", sa.String(length=64), nullable=False),
        sa.Column("raw_storage_key", sa.String(length=255), nullable=False),
        sa.Column("server_key", sa.String(length=255), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("original_folder", sa.String(length=255), nullable=False),
        sa.Column("current_folder", sa.String(length=255), nullable=False),
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
        sa.CheckConstraint("uidvalidity >= 1", name=op.f("ck_mail_messages_positive_uidvalidity")),
        sa.CheckConstraint("uid >= 1", name=op.f("ck_mail_messages_positive_uid")),
        sa.CheckConstraint("raw_size >= 1", name=op.f("ck_mail_messages_positive_raw_size")),
        sa.CheckConstraint(
            "status IN ('INGESTED')", name=op.f("ck_mail_messages_mail_message_status")
        ),
        sa.ForeignKeyConstraint(
            ["mail_account_id"],
            ["mail_accounts.id"],
            name=op.f("fk_mail_messages_mail_account_id_mail_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mail_messages")),
        sa.UniqueConstraint(
            "mail_account_id", "uidvalidity", "uid", name=op.f("uq_mail_messages_server_identity")
        ),
        sa.UniqueConstraint("raw_storage_key", name=op.f("uq_mail_messages_raw_storage_key")),
        sa.UniqueConstraint("server_key", name=op.f("uq_mail_messages_server_key")),
        sa.UniqueConstraint(
            "content_fingerprint", name=op.f("uq_mail_messages_content_fingerprint")
        ),
    )
    op.create_index(
        "ix_mail_messages_account_received", "mail_messages", ["mail_account_id", "received_at"]
    )
    op.create_index("ix_mail_messages_message_id", "mail_messages", ["message_id"])
    op.create_table(
        "mail_attachments",
        sa.Column("mail_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("content_id", sa.String(length=998), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("ordinal >= 0", name=op.f("ck_mail_attachments_nonnegative_ordinal")),
        sa.CheckConstraint("size >= 0", name=op.f("ck_mail_attachments_nonnegative_size")),
        sa.ForeignKeyConstraint(
            ["mail_message_id"],
            ["mail_messages.id"],
            name=op.f("fk_mail_attachments_mail_message_id_mail_messages"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mail_attachments")),
        sa.UniqueConstraint(
            "mail_message_id", "ordinal", name=op.f("uq_mail_attachments_message_ordinal")
        ),
        sa.UniqueConstraint("storage_key", name=op.f("uq_mail_attachments_storage_key")),
    )
    op.create_index(
        "ix_mail_attachments_message_sha256",
        "mail_attachments",
        ["mail_message_id", "sha256"],
    )


def downgrade() -> None:
    op.drop_index("ix_mail_attachments_message_sha256", table_name="mail_attachments")
    op.drop_table("mail_attachments")
    op.drop_index("ix_mail_messages_message_id", table_name="mail_messages")
    op.drop_index("ix_mail_messages_account_received", table_name="mail_messages")
    op.drop_table("mail_messages")
    op.drop_table("mail_accounts")
