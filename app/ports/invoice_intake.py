"""Replaceable boundaries for canonical invoice intake."""

from typing import Protocol
from uuid import UUID

from app.domain.intake.models import (
    InvoiceIntakeResult,
    InvoiceSubmissionCommand,
    SubmissionFileInput,
)


class InvoiceIntakeRepository(Protocol):
    def create_or_get(self, command: InvoiceSubmissionCommand) -> InvoiceIntakeResult: ...


class IMAPInvoiceSourceRepository(Protocol):
    def source_files(self, message_id: UUID) -> tuple[str, tuple[SubmissionFileInput, ...]]: ...
