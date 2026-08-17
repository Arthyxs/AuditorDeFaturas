"""Durable M15 semantic tariff-selection handler."""

from typing import Any, Protocol
from uuid import UUID

from app.domain.jobs import JobRecord
from app.domain.tariffs.selection import TariffSelectionRecord


class TariffSelector(Protocol):
    def select(self, invoice_id: UUID) -> TariffSelectionRecord: ...


class TariffSelectionJobHandler:
    def __init__(self, service: TariffSelector) -> None:
        self._service = service

    def __call__(self, job: JobRecord) -> None:
        self._service.select(self._uuid(job.payload, "invoice_id"))

    @staticmethod
    def _uuid(payload: dict[str, Any], key: str) -> UUID:
        try:
            return UUID(str(payload[key]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"tariff selection job {key} is invalid") from exc
