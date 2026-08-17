"""Durable M13 command for classification and safe IMAP movement."""

from typing import Any, Protocol
from uuid import UUID

from app.domain.jobs import JobRecord

EMAIL_CLASSIFICATION_JOB = "email.classify"


class EmailClassifier(Protocol):
    def classify_and_move(self, message_id: UUID): ...  # type: ignore[no-untyped-def]


class EmailClassificationJobHandler:
    def __init__(self, service: EmailClassifier) -> None:
        self._service = service

    def __call__(self, job: JobRecord) -> None:
        self._service.classify_and_move(self._uuid(job.payload, "mail_message_id"))

    @staticmethod
    def _uuid(payload: dict[str, Any], key: str) -> UUID:
        try:
            return UUID(str(payload[key]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"email classification job {key} is invalid") from exc
