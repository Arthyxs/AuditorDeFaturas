"""Persistence boundary for e-mail classification and movement state."""

from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.domain.email.classification import (
    ClassificationCandidate,
    EmailClassification,
    EmailClassificationOutput,
    EmailClassificationRecord,
)
from app.ports.email import EmailMessageLocator


class EmailClassificationRepository(Protocol):
    def get(self, message_id: UUID, *, lock: bool = False) -> ClassificationCandidate | None: ...

    def save_classification(
        self,
        message_id: UUID,
        *,
        output: EmailClassificationOutput,
        effective_classification: EmailClassification,
        threshold: Decimal,
        ai_call_id: UUID,
    ) -> EmailClassificationRecord: ...

    def mark_moved(
        self, message_id: UUID, *, locator: EmailMessageLocator
    ) -> EmailClassificationRecord: ...

    def mark_movement_error(
        self, message_id: UUID, *, code: str, detail: str
    ) -> EmailClassificationRecord: ...

    def list_manual_review(
        self, *, page: int, page_size: int
    ) -> tuple[list[EmailClassificationRecord], int]: ...

    def resolve_manual_review(
        self,
        message_id: UUID,
        *,
        classification: EmailClassification,
        reviewer_id: UUID,
        note: str | None,
    ) -> EmailClassificationRecord: ...
