"""Establish the initial Alembic migration lineage.

Revision ID: 20260816_0001
Revises: None
Create Date: 2026-08-16
"""

from collections.abc import Sequence

revision: str = "20260816_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Reserve the base revision; product tables belong to later milestones."""


def downgrade() -> None:
    """Return to the pre-Alembic base revision."""
