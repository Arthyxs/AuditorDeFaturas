"""M13 e-mail classification, confidence review routing and safe movement."""

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, cast
from uuid import UUID

from app.application.services.ai import AIExecutionResult
from app.domain.email.classification import (
    ClassificationCandidate,
    EmailClassification,
    EmailClassificationOutput,
    EmailClassificationRecord,
)
from app.ports.ai import AIInvalidResponseError, AIMessage, AIRequest, AITask
from app.ports.email import EmailMessage, EmailMessageLocator, EmailProvider, EmailProviderError
from app.ports.email_classification import EmailClassificationRepository


class ClassificationAIExecutor(Protocol):
    def execute(
        self, *, provider: str, model: str, request: AIRequest, audit_run_id: UUID | None = None
    ) -> AIExecutionResult: ...


class ClassificationPromptProvider(Protocol):
    def load(self, name: str, version: str): ...  # type: ignore[no-untyped-def]


@dataclass(frozen=True)
class ClassificationFolders:
    invoice: str
    due_notice: str
    general: str
    manual_review: str

    def for_classification(self, value: EmailClassification) -> str:
        return {
            EmailClassification.INVOICE: self.invoice,
            EmailClassification.DUE_NOTICE: self.due_notice,
            EmailClassification.GENERAL: self.general,
            EmailClassification.MANUAL_REVIEW: self.manual_review,
        }[value]


class EmailClassificationService:
    """Persist classification before moving so every external failure is safely retryable."""

    def __init__(
        self,
        *,
        repository: EmailClassificationRepository,
        email_provider: EmailProvider,
        ai: ClassificationAIExecutor,
        prompt_provider: ClassificationPromptProvider,
        provider: str,
        model: str,
        min_confidence: Decimal,
        folders: ClassificationFolders,
        thread_max_messages: int,
        thread_max_characters: int,
    ) -> None:
        self._repository = repository
        self._email_provider = email_provider
        self._ai = ai
        self._prompt_provider = prompt_provider
        self._provider = provider
        self._model = model
        self._min_confidence = min_confidence
        self._folders = folders
        self._thread_max_messages = thread_max_messages
        self._thread_max_characters = thread_max_characters

    def classify_and_move(self, message_id: UUID) -> EmailClassificationRecord:
        candidate = self._repository.get(message_id)
        if candidate is None:
            raise LookupError("mail message not found")
        if candidate.classification is None:
            output, call_id = self._classify(candidate)
            known_ids = {attachment.id for attachment in candidate.attachments}
            chosen_ids = set(output.invoice_attachment_ids) | set(output.supporting_attachment_ids)
            if not chosen_ids <= known_ids or set(output.invoice_attachment_ids) & set(
                output.supporting_attachment_ids
            ):
                raise AIInvalidResponseError("classification referenced invalid attachment IDs")
            effective = (
                EmailClassification.MANUAL_REVIEW
                if output.confidence < self._min_confidence
                else output.classification
            )
            self._repository.save_classification(
                message_id,
                output=output,
                effective_classification=effective,
                threshold=self._min_confidence,
                ai_call_id=call_id,
            )
            candidate = self._repository.get(message_id)
            if candidate is None or candidate.classification is None:
                raise RuntimeError("classification disappeared after persistence")

        locator = EmailMessageLocator(
            folder=candidate.locator_folder,
            uidvalidity=candidate.uidvalidity,
            uid=candidate.uid,
        )
        if candidate.moved_at is not None:
            return self._repository.mark_moved(message_id, locator=locator)
        destination = self._folders.for_classification(candidate.classification)
        try:
            moved = self._email_provider.move_message(locator, destination)
        except EmailProviderError as exc:
            self._repository.mark_movement_error(
                message_id,
                code="IMAP_ERROR",
                detail=self._safe_error(exc),
            )
            raise
        return self._repository.mark_moved(message_id, locator=moved)

    def move_reviewed(self, message_id: UUID) -> EmailClassificationRecord:
        """Move a human-resolved message without making another classification call."""
        candidate = self._repository.get(message_id)
        if candidate is None or candidate.classification is None:
            raise LookupError("classified mail message not found")
        return self.classify_and_move(message_id)

    def _classify(
        self, candidate: ClassificationCandidate
    ) -> tuple[EmailClassificationOutput, UUID]:
        locator = EmailMessageLocator(
            folder=candidate.locator_folder,
            uidvalidity=candidate.uidvalidity,
            uid=candidate.uid,
        )
        context = self._email_provider.get_thread_context(
            locator,
            max_messages=self._thread_max_messages,
            max_characters=self._thread_max_characters,
        )
        payload = {
            "current": self._message_payload(context.current),
            "history": [self._message_payload(message) for message in context.history],
            "thread_truncated": context.truncated,
            "attachment_catalog": [
                {
                    "id": str(item.id),
                    "filename": item.filename,
                    "mime_type": item.mime_type,
                    "size": item.size,
                }
                for item in candidate.attachments
            ],
        }
        request = AIRequest(
            task=AITask.EMAIL_CLASSIFICATION,
            prompt=self._prompt_provider.load("email_classification", "1"),
            messages=(AIMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),),
            output_model=EmailClassificationOutput,
        )
        executed = self._ai.execute(provider=self._provider, model=self._model, request=request)
        output = cast(EmailClassificationOutput, executed.result.output)
        return output, executed.call_id

    @staticmethod
    def _message_payload(message: EmailMessage) -> dict[str, object]:
        return {
            "message_id": message.message_id,
            "in_reply_to": message.in_reply_to,
            "references": list(message.references),
            "headers": [list(value) for value in message.headers],
            "subject": message.subject,
            "sender": message.sender,
            "recipients": list(message.recipients),
            "body_text": message.body_text,
            "body_html": message.body_html,
            "attachments": [
                {
                    "filename": item.filename,
                    "mime_type": item.mime_type,
                    "content_id": item.content_id,
                    "disposition": item.disposition,
                }
                for item in message.attachments
            ],
        }

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        value = str(exc).replace("\r", " ").replace("\n", " ")[:4000]
        if any(marker in value.casefold() for marker in ("password", "secret", "token", "://")):
            return "sensitive IMAP error detail redacted"
        return value or type(exc).__name__
