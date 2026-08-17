"""Add the immutable tariff catalog.

Revision ID: 20260817_0003
Revises: 20260816_0002
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0003"
down_revision: str | None = "20260816_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tariff metadata without making stored blobs mutable."""
    op.create_table(
        "tariff_files",
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("internal_filename", sa.String(length=255), nullable=False),
        sa.Column("extension", sa.String(length=16), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("version_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("size > 0", name=op.f("ck_tariff_files_positive_size")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_tariff_files_positive_version")),
        sa.ForeignKeyConstraint(
            ["previous_version_id"],
            ["tariff_files.id"],
            name=op.f("fk_tariff_files_previous_version_id_tariff_files"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"],
            ["users.id"],
            name=op.f("fk_tariff_files_uploaded_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tariff_files")),
        sa.UniqueConstraint(
            "previous_version_id", name=op.f("uq_tariff_files_previous_version_id")
        ),
        sa.UniqueConstraint("storage_key", name=op.f("uq_tariff_files_storage_key")),
    )
    op.create_index(op.f("ix_tariff_files_sha256"), "tariff_files", ["sha256"])
    op.create_index(op.f("ix_tariff_files_uploaded_by_id"), "tariff_files", ["uploaded_by_id"])
    op.create_index(op.f("ix_tariff_files_version_group_id"), "tariff_files", ["version_group_id"])
    op.create_index(
        "ix_tariff_files_catalog",
        "tariff_files",
        ["deleted_at", "active", "created_at"],
    )


def downgrade() -> None:
    """Remove tariff metadata; stored blobs remain outside migration control."""
    op.drop_index("ix_tariff_files_catalog", table_name="tariff_files")
    op.drop_index(op.f("ix_tariff_files_version_group_id"), table_name="tariff_files")
    op.drop_index(op.f("ix_tariff_files_uploaded_by_id"), table_name="tariff_files")
    op.drop_index(op.f("ix_tariff_files_sha256"), table_name="tariff_files")
    op.drop_table("tariff_files")
