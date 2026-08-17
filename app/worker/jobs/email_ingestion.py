"""Durable job command for one canonical e-mail ingestion."""

from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from app.domain.email.models import EmailIngestionResult
from app.domain.jobs import JobRecord
from app.ports.email import EmailMessageLocator
from app.ports.jobs import JobQueue
from app.worker.jobs.email_classification import EMAIL_CLASSIFICATION_JOB

EMAIL_INGESTION_JOB = "email.ingest"


class EmailIngestor(Protocol):
    def ingest(
        self, *, mail_account_id: UUID, locator: EmailMessageLocator
    ) -> EmailIngestionResult: ...


class EmailIngestionJobHandler:
    """Validate durable payload identity before invoking the ingestion use case."""

    def __init__(
        self,
        service: EmailIngestor,
        *,
        classification_queue: JobQueue | None = None,
        max_attempts: int = 5,
    ) -> None:
        self._service = service
        self._classification_queue = classification_queue
        self._max_attempts = max_attempts

    def __call__(self, job: JobRecord) -> None:
        payload = job.payload
        account_id = self._uuid(payload, "mail_account_id")
        folder = self._string(payload, "folder")
        uidvalidity = self._positive_integer(payload, "uidvalidity")
        uid = self._positive_integer(payload, "uid")
        result = self._service.ingest(
            mail_account_id=account_id,
            locator=EmailMessageLocator(folder=folder, uidvalidity=uidvalidity, uid=uid),
        )
        if self._classification_queue is not None:
            self._classification_queue.enqueue(
                job_type=EMAIL_CLASSIFICATION_JOB,
                idempotency_key=f"email.classify:{result.message.id}",
                payload={"mail_message_id": str(result.message.id)},
                max_attempts=self._max_attempts,
                available_at=datetime.now(UTC),
                priority=10,
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
