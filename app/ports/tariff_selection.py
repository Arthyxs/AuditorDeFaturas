"""Persistence boundary for semantic tariff selection."""

from contextlib import AbstractContextManager
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.domain.tariffs.selection import (
    TariffSelectionContext,
    TariffSelectionRecord,
    TariffSelectionStatus,
)


class TariffSelectionRepository(Protocol):
    def selection_guard(self, invoice_id: UUID) -> AbstractContextManager[None]: ...

    def context(self, invoice_id: UUID) -> TariffSelectionContext | None: ...

    def existing(self, invoice_id: UUID) -> TariffSelectionRecord | None: ...

    def save(
        self,
        invoice_id: UUID,
        *,
        status: TariffSelectionStatus,
        selected_tariff_ids: tuple[UUID, ...],
        confidence: Decimal | None,
        threshold: Decimal,
        reason: str,
        ai_call_id: UUID | None,
    ) -> TariffSelectionRecord: ...

    def selected_storage_keys(self, invoice_id: UUID) -> tuple[str, ...]: ...
