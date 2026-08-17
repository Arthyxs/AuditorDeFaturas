"""Canonical invoice intake models shared by IMAP and manual origins."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SubmissionSource(StrEnum):
    IMAP = "IMAP"
    MANUAL = "MANUAL"


class SubmissionFileRole(StrEnum):
    INVOICE = "INVOICE"
    AUXILIARY = "AUXILIARY"


class ChargeItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name_raw: str = Field(min_length=1, max_length=255)
    name_normalized: str | None = Field(default=None, max_length=255)
    charged_amount: Decimal | None = None

    @field_validator("charged_amount", mode="before")
    @classmethod
    def reject_float_money(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("money must be provided as a decimal string")
        return value


class InvoiceDocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: str | None = Field(default=None, max_length=64)
    document_number: str | None = Field(default=None, max_length=255)
    issue_date: date | None = None
    origin_city: str | None = Field(default=None, max_length=255)
    origin_state: str | None = Field(default=None, max_length=64)
    destination_city: str | None = Field(default=None, max_length=255)
    destination_state: str | None = Field(default=None, max_length=64)
    origin_zip: str | None = Field(default=None, max_length=32)
    destination_zip: str | None = Field(default=None, max_length=32)
    real_weight: Decimal | None = None
    cubic_weight: Decimal | None = None
    chargeable_weight: Decimal | None = None
    merchandise_value: Decimal | None = None
    amount_charged: Decimal | None = None
    our_freight_revenue: Decimal | None = None
    source_reference: dict[str, Any] = Field(default_factory=dict)
    charge_items: list[ChargeItemInput] = Field(default_factory=list, max_length=1000)

    @field_validator(
        "real_weight",
        "cubic_weight",
        "chargeable_weight",
        "merchandise_value",
        "amount_charged",
        "our_freight_revenue",
        mode="before",
    )
    @classmethod
    def reject_float_decimal(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("decimal values must be provided as strings")
        return value


class InvoiceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    partner_name: str | None = Field(default=None, max_length=255)
    partner_document_id: str | None = Field(default=None, max_length=64)
    invoice_number: str | None = Field(default=None, max_length=255)
    issue_date: date | None = None
    due_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    amount_charged: Decimal | None = None
    documents: list[InvoiceDocumentInput] = Field(default_factory=list, max_length=1000)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("amount_charged", mode="before")
    @classmethod
    def reject_float_money(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("money must be provided as a decimal string")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else None


@dataclass(frozen=True)
class SubmissionFileInput:
    role: SubmissionFileRole
    ordinal: int
    original_filename: str
    mime_type: str
    size: int
    sha256: str
    storage_key: str


@dataclass(frozen=True)
class InvoiceSubmissionCommand:
    source: SubmissionSource
    idempotency_key: str
    content_hash: str
    mail_message_id: UUID | None
    submitted_by_id: UUID | None
    files: tuple[SubmissionFileInput, ...]
    metadata: InvoiceMetadata
    note: str | None


@dataclass(frozen=True)
class InvoiceRecord:
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


@dataclass(frozen=True)
class InvoiceIntakeResult:
    invoice: InvoiceRecord
    created: bool
