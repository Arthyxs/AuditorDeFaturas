"""M14 invoice intake API responses."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.intake.models import SubmissionSource


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    submission_id: UUID
    source: SubmissionSource
    partner_id: UUID | None
    partner_name_raw: str | None
    invoice_number: str | None
    issue_date: date | None
    due_date: date | None
    currency: str | None
    amount_charged: Decimal | None
    status: str
    document_count: int
    created_at: datetime


class ManualInvoiceResponse(BaseModel):
    invoice: InvoiceResponse
    created: bool
