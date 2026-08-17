"""M15 semantic tariff-selection and explicit pending state."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.persistence.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class TariffSelectionRun(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "tariff_selection_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('SELECTED', 'NO_TARIFF', 'LOW_CONFIDENCE')",
            name="tariff_selection_status",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="tariff_selection_confidence",
        ),
        CheckConstraint("threshold >= 0 AND threshold <= 1", name="tariff_selection_threshold"),
    )

    invoice_id: Mapped[UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    threshold: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    ai_call_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ai_calls.id", ondelete="RESTRICT"), nullable=True
    )

    files: Mapped[list["TariffSelectionFile"]] = relationship(
        back_populates="selection_run", cascade="all, delete-orphan"
    )


class TariffSelectionFile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "tariff_selection_files"
    __table_args__ = (
        UniqueConstraint("selection_run_id", "tariff_file_id", name="uq_selection_tariff_file"),
    )

    selection_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("tariff_selection_runs.id", ondelete="RESTRICT"), nullable=False
    )
    tariff_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("tariff_files.id", ondelete="RESTRICT"), nullable=False
    )

    selection_run: Mapped[TariffSelectionRun] = relationship(back_populates="files")


class PendingItem(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "pending_items"
    __table_args__ = (
        UniqueConstraint("invoice_id", "type", name="uq_pending_items_invoice_type"),
        CheckConstraint("status IN ('OPEN', 'RESOLVED', 'DISMISSED')", name="pending_status"),
    )

    invoice_id: Mapped[UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("invoice_documents.id", ondelete="RESTRICT"), nullable=True
    )
    audit_run_id: Mapped[UUID | None] = mapped_column(nullable=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    required_information: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")
