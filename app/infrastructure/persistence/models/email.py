"""Immutable e-mail originals and mutable server-location metadata."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
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

from app.infrastructure.persistence.models.base import (
    Base,
    CreatedAtMixin,
    UpdatedAtMixin,
    UUIDPrimaryKeyMixin,
)


class MailAccount(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """Configured mailbox identity without its secret."""

    __tablename__ = "mail_accounts"
    __table_args__ = (
        UniqueConstraint("host", "port", "username", name="uq_mail_accounts_mailbox_identity"),
        CheckConstraint("port >= 1 AND port <= 65535", name="valid_port"),
    )

    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    username: Mapped[str] = mapped_column(String(320), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    messages: Mapped[list["MailMessage"]] = relationship(back_populates="mail_account")


class MailMessage(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """One canonical message with exact RFC source stored append-only."""

    __tablename__ = "mail_messages"
    __table_args__ = (
        UniqueConstraint(
            "mail_account_id",
            "uidvalidity",
            "uid",
            name="uq_mail_messages_server_identity",
        ),
        CheckConstraint("uidvalidity >= 1", name="positive_uidvalidity"),
        CheckConstraint("uid >= 1", name="positive_uid"),
        CheckConstraint("raw_size >= 1", name="positive_raw_size"),
        CheckConstraint(
            "status IN ('INGESTED', 'CLASSIFIED', 'MOVED', 'MANUAL_REVIEW', 'ERROR')",
            name="mail_message_status",
        ),
        CheckConstraint(
            "classification IS NULL OR classification IN "
            "('INVOICE', 'DUE_NOTICE', 'GENERAL', 'MANUAL_REVIEW')",
            name="mail_message_classification",
        ),
        CheckConstraint(
            "classification_confidence IS NULL OR "
            "(classification_confidence >= 0 AND classification_confidence <= 1)",
            name="classification_confidence_range",
        ),
        CheckConstraint(
            "classification_threshold IS NULL OR "
            "(classification_threshold >= 0 AND classification_threshold <= 1)",
            name="classification_threshold_range",
        ),
        Index("ix_mail_messages_account_received", "mail_account_id", "received_at"),
        Index("ix_mail_messages_message_id", "message_id"),
        Index("ix_mail_messages_manual_review", "status", "created_at"),
    )

    mail_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("mail_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    uidvalidity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[str | None] = mapped_column(String(998), nullable=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(998), nullable=True)
    references: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_subject: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str] = mapped_column(String(998), nullable=False)
    normalized_sender: Mapped[str] = mapped_column(String(998), nullable=False)
    recipients: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    headers: Mapped[list[list[str]]] = mapped_column(JSONB, nullable=False, default=list)
    header_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raw_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    server_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="INGESTED")
    original_folder: Mapped[str] = mapped_column(String(255), nullable=False)
    current_folder: Mapped[str] = mapped_column(String(255), nullable=False)
    classification: Mapped[str | None] = mapped_column(String(32), nullable=True)
    classification_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    classification_threshold: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    partner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    partner_document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invoice_attachment_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    supporting_attachment_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    classification_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification_evidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    classification_ai_call_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ai_calls.id", ondelete="RESTRICT"), nullable=True
    )
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    moved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processing_error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    mail_account: Mapped[MailAccount] = relationship(back_populates="messages")
    attachments: Mapped[list["MailAttachment"]] = relationship(
        back_populates="mail_message",
        cascade="all, delete-orphan",
        order_by="MailAttachment.ordinal",
    )


class MailAttachment(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Immutable storage reference for one MIME attachment part."""

    __tablename__ = "mail_attachments"
    __table_args__ = (
        UniqueConstraint("mail_message_id", "ordinal", name="uq_mail_attachments_message_ordinal"),
        CheckConstraint("ordinal >= 0", name="nonnegative_ordinal"),
        CheckConstraint("size >= 0", name="nonnegative_size"),
        Index("ix_mail_attachments_message_sha256", "mail_message_id", "sha256"),
    )

    mail_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("mail_messages.id", ondelete="RESTRICT"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    content_id: Mapped[str | None] = mapped_column(String(998), nullable=True)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    mail_message: Mapped[MailMessage] = relationship(back_populates="attachments")
