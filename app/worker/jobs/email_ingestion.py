"""Durable job command for one canonical e-mail ingestion."""

from typing import Any, Protocol
from uuid import UUID

from app.domain.email.models import EmailIngestionResult
from app.domain.jobs import JobRecord
from app.ports.email import EmailMessageLocator

EMAIL_INGESTION_JOB = "email.ingest"


class EmailIngestor(Protocol):
    def ingest(
        self, *, mail_account_id: UUID, locator: EmailMessageLocator
    ) -> EmailIngestionResult: ...


class EmailIngestionJobHandler:
    """Validate durable payload identity before invoking the ingestion use case."""

    def __init__(self, service: EmailIngestor) -> None:
        self._service = service

    def __call__(self, job: JobRecord) -> None:
        payload = job.payload
        account_id = self._uuid(payload, "mail_account_id")
        folder = self._string(payload, "folder")
        uidvalidity = self._positive_integer(payload, "uidvalidity")
        uid = self._positive_integer(payload, "uid")
        self._service.ingest(
            mail_account_id=account_id,
            locator=EmailMessageLocator(folder=folder, uidvalidity=uidvalidity, uid=uid),
        )

    @staticmethod
    def _uuid(payload: dict[str, Any], key: str) -> UUID:
        try:
            return UUID(str(payload[key]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"email ingestion job {key} is invalid") from exc

    @staticmethod
    def _string(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"email ingestion job {key} is invalid")
        return value

    @staticmethod
    def _positive_integer(payload: dict[str, Any], key: str) -> int:
        value = payload.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"email ingestion job {key} is invalid")
        return value
