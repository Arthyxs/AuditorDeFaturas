"""Provider-neutral semantic tariff-selection contracts."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TariffSelectionStatus(StrEnum):
    SELECTED = "SELECTED"
    NO_TARIFF = "NO_TARIFF"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class TariffSelectionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_tariff_ids: list[UUID] = Field(default_factory=list, max_length=100)
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator("selected_tariff_ids")
    @classmethod
    def unique_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("selected tariff IDs must be unique")
        return value


@dataclass(frozen=True)
class TariffCandidate:
    id: UUID
    original_filename: str
    extension: str
    description: str | None
    notes: str | None
    version: int
    created_at: datetime


@dataclass(frozen=True)
class TariffSelectionContext:
    invoice_id: UUID
    partner_name: str | None
    invoice_number: str | None
    issue_date: date | None
    due_date: date | None
    currency: str | None
    amount_charged: Decimal | None
    documents: tuple[dict[str, Any], ...]
    candidates: tuple[TariffCandidate, ...]


@dataclass(frozen=True)
class TariffSelectionRecord:
    invoice_id: UUID
    status: TariffSelectionStatus
    selected_tariff_ids: tuple[UUID, ...]
    confidence: Decimal | None
    threshold: Decimal
    reason: str
    ai_call_id: UUID | None
    created_at: datetime
