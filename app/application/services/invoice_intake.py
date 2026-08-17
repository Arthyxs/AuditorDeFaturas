"""Canonical M14 invoice intake shared by manual and IMAP adapters."""

import json
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from app.domain.intake.models import (
    InvoiceIntakeResult,
    InvoiceMetadata,
    InvoiceSubmissionCommand,
    SubmissionFileInput,
    SubmissionSource,
)
from app.ports.invoice_intake import IMAPInvoiceSourceRepository, InvoiceIntakeRepository
from app.ports.jobs import JobQueue
from app.worker.jobs.invoice_intake import TARIFF_SELECTION_JOB


def canonical_submission_hash(
    *, source: SubmissionSource, files: tuple[SubmissionFileInput, ...], metadata: InvoiceMetadata
) -> str:
    payload = {
        "source": source.value,
        "files": [
            {"role": item.role.value, "ordinal": item.ordinal, "sha256": item.sha256}
            for item in files
        ],
        "metadata": metadata.model_dump(mode="json"),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


class InvoiceIntakeService:
    def __init__(
        self, *, repository: InvoiceIntakeRepository, queue: JobQueue, max_attempts: int
    ) -> None:
        self._repository = repository
        self._queue = queue
        self._max_attempts = max_attempts

    def submit(self, command: InvoiceSubmissionCommand) -> InvoiceIntakeResult:
        if not command.files or not any(item.role.value == "INVOICE" for item in command.files):
            raise ValueError("invoice submission requires at least one invoice original")
        result = self._repository.create_or_get(command)
        self._queue.enqueue(
            job_type=TARIFF_SELECTION_JOB,
            idempotency_key=f"invoice.select-tariffs:{result.invoice.id}",
            payload={"invoice_id": str(result.invoice.id)},
            max_attempts=self._max_attempts,
            available_at=datetime.now(UTC),
            priority=10,
        )
        return result


class IMAPInvoiceIntakeAdapter:
    def __init__(
        self, *, source_repository: IMAPInvoiceSourceRepository, intake: InvoiceIntakeService
    ) -> None:
        self._source_repository = source_repository
        self._intake = intake

    def submit_invoice_email(
        self,
        message_id: UUID,
        *,
        partner_name: str | None,
        partner_document_id: str | None,
    ) -> InvoiceIntakeResult:
        fingerprint, files = self._source_repository.source_files(message_id)
        metadata = InvoiceMetadata(
            partner_name=partner_name,
            partner_document_id=partner_document_id,
        )
        return self._intake.submit(
            InvoiceSubmissionCommand(
                source=SubmissionSource.IMAP,
                idempotency_key=f"imap:{message_id}",
                content_hash=fingerprint,
                mail_message_id=message_id,
                submitted_by_id=None,
                files=files,
                metadata=metadata,
                note=None,
            )
        )
