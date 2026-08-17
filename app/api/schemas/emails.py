"""API schemas for the minimal M13 manual classification review surface."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.email.classification import EmailClassification


class EmailReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class EmailReviewListResponse(BaseModel):
    items: list[EmailReviewResponse]
    page: int
    page_size: int
    total: int
    pages: int


class EmailReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: EmailClassification
    note: str | None = Field(default=None, max_length=4000)
