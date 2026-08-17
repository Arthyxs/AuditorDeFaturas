"""M14 canonical invoice submission, partner and invoice persistence."""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.persistence.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class Partner(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "partners"

    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class InvoiceSubmission(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "invoice_submissions"
    __table_args__ = (
        CheckConstraint("source_type IN ('IMAP', 'MANUAL')", name="submission_source"),
        CheckConstraint(
            "(source_type = 'IMAP' AND mail_message_id IS NOT NULL AND submitted_by_id IS NULL) OR "
            "(source_type = 'MANUAL' AND mail_message_id IS NULL AND submitted_by_id IS NOT NULL)",
            name="submission_origin_reference",
        ),
        CheckConstraint("status IN ('ACCEPTED')", name="submission_status"),
    )

    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    mail_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("mail_messages.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    submitted_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACCEPTED")

    files: Mapped[list["SubmissionFile"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", order_by="SubmissionFile.ordinal"
    )
    invoice: Mapped["Invoice"] = relationship(back_populates="submission", uselist=False)


class SubmissionFile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "submission_files"
    __table_args__ = (
        UniqueConstraint("submission_id", "ordinal", name="uq_submission_files_ordinal"),
        CheckConstraint("role IN ('INVOICE', 'AUXILIARY')", name="submission_file_role"),
        CheckConstraint("ordinal >= 0", name="submission_file_ordinal"),
        CheckConstraint("size >= 0", name="submission_file_size"),
    )

    submission_id: Mapped[UUID] = mapped_column(
        ForeignKey("invoice_submissions.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    submission: Mapped[InvoiceSubmission] = relationship(back_populates="files")


class Invoice(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PROCESSING', 'CORRECT', 'INCORRECT', 'PENDING', "
            "'MANUAL_REVIEW', 'NOT_AUDITABLE', 'ERROR')",
            name="invoice_status",
        ),
        Index("ix_invoices_status_created", "status", "created_at"),
    )

    submission_id: Mapped[UUID] = mapped_column(
        ForeignKey("invoice_submissions.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    mail_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("mail_messages.id", ondelete="RESTRICT"), nullable=True
    )
    partner_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("partners.id", ondelete="RESTRICT"), nullable=True
    )
    partner_name_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    amount_charged: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    amount_expected: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    difference: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PROCESSING")

    submission: Mapped[InvoiceSubmission] = relationship(back_populates="invoice")
    documents: Mapped[list["InvoiceDocument"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceDocument(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "invoice_documents"
    __table_args__ = (
        Index("ix_invoice_documents_invoice_number", "invoice_id", "document_number"),
    )

    invoice_id: Mapped[UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False
    )
    document_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    origin_city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    origin_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    destination_city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    destination_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    origin_zip: Mapped[str | None] = mapped_column(String(32), nullable=True)
    destination_zip: Mapped[str | None] = mapped_column(String(32), nullable=True)
    real_weight: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    cubic_weight: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    chargeable_weight: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    merchandise_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    amount_charged: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    amount_expected: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    difference: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    our_freight_revenue: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    gross_margin_actual: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    gross_margin_expected: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_reference: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    invoice: Mapped[Invoice] = relationship(back_populates="documents")
    charge_items: Mapped[list["DocumentChargeItem"]] = relationship(
        back_populates="invoice_document", cascade="all, delete-orphan"
    )


class DocumentChargeItem(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "document_charge_items"

    invoice_document_id: Mapped[UUID] = mapped_column(
        ForeignKey("invoice_documents.id", ondelete="RESTRICT"), nullable=False
    )
    name_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    name_normalized: Mapped[str | None] = mapped_column(String(255), nullable=True)
    charged_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    expected_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    difference: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    invoice_document: Mapped[InvoiceDocument] = relationship(back_populates="charge_items")
