"""Provider-neutral e-mail classification contracts and lifecycle records."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EmailClassification(StrEnum):
    INVOICE = "INVOICE"
    DUE_NOTICE = "DUE_NOTICE"
    GENERAL = "GENERAL"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class PartnerGuess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=255)
    document_id: str | None = Field(default=None, max_length=64)


class EmailClassificationOutput(BaseModel):
    """Strict structured output requested from the classification model."""

    model_config = ConfigDict(extra="forbid")

    classification: EmailClassification
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    partner: PartnerGuess = Field(default_factory=PartnerGuess)
    invoice_attachment_ids: list[UUID] = Field(default_factory=list)
    supporting_attachment_ids: list[UUID] = Field(default_factory=list)
    summary: str = Field(min_length=1, max_length=4000)
    evidence: list[str] = Field(min_length=1, max_length=50)


@dataclass(frozen=True)
class ClassificationAttachment:
    id: UUID
    filename: str
    mime_type: str
    size: int


@dataclass(frozen=True)
class ClassificationCandidate:
    id: UUID
    mail_account_id: UUID
    locator_folder: str
    uidvalidity: int
    uid: int
    subject: str
    sender: str
    recipients: tuple[str, ...]
    body_text: str | None
    body_html: str | None
    attachments: tuple[ClassificationAttachment, ...]
    classification: EmailClassification | None
    classification_confidence: Decimal | None
    classification_threshold: Decimal | None
    moved_at: datetime | None
    status: str


@dataclass(frozen=True)
class EmailClassificationRecord:
    id: UUID
    classification: EmailClassification
    confidence: Decimal
    threshold: Decimal
    partner_name: str | None
    partner_document_id: str | None
    invoice_attachment_ids: tuple[UUID, ...]
    supporting_attachment_ids: tuple[UUID, ...]
    summary: str
    evidence: tuple[str, ...]
    status: str
    current_folder: str
    moved_at: datetime | None
    error_code: str | None
    error_detail: str | None
