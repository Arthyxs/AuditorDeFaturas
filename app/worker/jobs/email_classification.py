"""Durable M13 command for classification and safe IMAP movement."""

from typing import Any, Protocol
from uuid import UUID

from app.domain.email.classification import EmailClassification, EmailClassificationRecord
from app.domain.jobs import JobRecord

EMAIL_CLASSIFICATION_JOB = "email.classify"


class EmailClassifier(Protocol):
    def classify_and_move(self, message_id: UUID) -> EmailClassificationRecord: ...


class InvoiceEmailIntake(Protocol):
    def submit_invoice_email(
        self,
        message_id: UUID,
        *,
        partner_name: str | None,
        partner_document_id: str | None,
    ) -> object: ...


class EmailClassificationJobHandler:
    def __init__(
        self, service: EmailClassifier, *, invoice_intake: InvoiceEmailIntake | None = None
    ) -> None:
        self._service = service
        self._invoice_intake = invoice_intake

    def __call__(self, job: JobRecord) -> None:
        message_id = self._uuid(job.payload, "mail_message_id")
        result = self._service.classify_and_move(message_id)
        if (
            result.classification is EmailClassification.INVOICE
            and self._invoice_intake is not None
        ):
            self._invoice_intake.submit_invoice_email(
                message_id,
                partner_name=result.partner_name,
                partner_document_id=result.partner_document_id,
            )

    @staticmethod
    def _uuid(payload: dict[str, Any], key: str) -> UUID:
        try:
            return UUID(str(payload[key]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"email classification job {key} is invalid") from exc
