"""PostgreSQL adapter for M13 classification and movement state."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select

from app.domain.email.classification import (
    ClassificationAttachment,
    ClassificationCandidate,
    EmailClassification,
    EmailClassificationOutput,
    EmailClassificationRecord,
)
from app.infrastructure.persistence.models import MailMessage
from app.infrastructure.persistence.session import SessionFactory, session_scope
from app.ports.email import EmailMessageLocator


class PostgreSQLEmailClassificationRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get(self, message_id: UUID, *, lock: bool = False) -> ClassificationCandidate | None:
        with session_scope(self._session_factory) as database:
            statement = select(MailMessage).where(MailMessage.id == message_id)
            if lock:
                statement = statement.with_for_update()
            model = database.scalar(statement)
            return None if model is None else self._candidate(model)

    def save_classification(
        self,
        message_id: UUID,
        *,
        output: EmailClassificationOutput,
        effective_classification: EmailClassification,
        threshold: Decimal,
        ai_call_id: UUID,
    ) -> EmailClassificationRecord:
        with session_scope(self._session_factory) as database:
            model = database.scalar(
                select(MailMessage).where(MailMessage.id == message_id).with_for_update()
            )
            if model is None:
                raise LookupError("mail message not found")
            if model.classification is None:
                now = datetime.now(UTC)
                model.classification = effective_classification.value
                model.classification_confidence = output.confidence
                model.classification_threshold = threshold
                model.partner_name = output.partner.name
                model.partner_document_id = output.partner.document_id
                model.invoice_attachment_ids = [
                    str(value) for value in output.invoice_attachment_ids
                ]
                model.supporting_attachment_ids = [
                    str(value) for value in output.supporting_attachment_ids
                ]
                model.classification_summary = output.summary
                model.classification_evidence = output.evidence
                model.classification_ai_call_id = ai_call_id
                model.classified_at = now
                model.status = (
                    "MANUAL_REVIEW"
                    if effective_classification is EmailClassification.MANUAL_REVIEW
                    else "CLASSIFIED"
                )
                model.processing_error_code = None
                model.processing_error_detail = None
                database.flush()
            return self._record(model)

    def mark_moved(
        self, message_id: UUID, *, locator: EmailMessageLocator
    ) -> EmailClassificationRecord:
        with session_scope(self._session_factory) as database:
            model = database.scalar(
                select(MailMessage).where(MailMessage.id == message_id).with_for_update()
            )
            if model is None or model.classification is None:
                raise LookupError("classified mail message not found")
            if model.moved_at is None:
                model.current_folder = locator.folder
                model.uidvalidity = locator.uidvalidity
                model.uid = locator.uid
                model.moved_at = datetime.now(UTC)
                model.status = (
                    "MANUAL_REVIEW"
                    if model.classification == EmailClassification.MANUAL_REVIEW.value
                    else "MOVED"
                )
                model.processing_error_code = None
                model.processing_error_detail = None
                database.flush()
            return self._record(model)

    def mark_movement_error(
        self, message_id: UUID, *, code: str, detail: str
    ) -> EmailClassificationRecord:
        with session_scope(self._session_factory) as database:
            model = database.scalar(
                select(MailMessage).where(MailMessage.id == message_id).with_for_update()
            )
            if model is None:
                raise LookupError("mail message not found")
            model.status = "ERROR"
            model.processing_error_code = code[:64]
            model.processing_error_detail = detail[:4000]
            database.flush()
            return self._record(model)

    def list_manual_review(
        self, *, page: int, page_size: int
    ) -> tuple[list[EmailClassificationRecord], int]:
        with session_scope(self._session_factory) as database:
            filters = (MailMessage.classification == EmailClassification.MANUAL_REVIEW.value,)
            total = database.scalar(select(func.count()).select_from(MailMessage).where(*filters))
            models = database.scalars(
                select(MailMessage)
                .where(*filters)
                .order_by(MailMessage.created_at, MailMessage.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return [self._record(model) for model in models], int(total or 0)

    def resolve_manual_review(
        self,
        message_id: UUID,
        *,
        classification: EmailClassification,
        reviewer_id: UUID,
        note: str | None,
    ) -> EmailClassificationRecord:
        if classification is EmailClassification.MANUAL_REVIEW:
            raise ValueError("manual review must resolve to a conclusive e-mail class")
        with session_scope(self._session_factory) as database:
            model = database.scalar(
                select(MailMessage).where(MailMessage.id == message_id).with_for_update()
            )
            if model is None:
                raise LookupError("mail message not found")
            if model.classification != EmailClassification.MANUAL_REVIEW.value:
                raise ValueError("mail message is not awaiting manual review")
            model.classification = classification.value
            model.status = "CLASSIFIED"
            model.reviewed_by_id = reviewer_id
            model.review_note = note
            model.reviewed_at = datetime.now(UTC)
            model.moved_at = None
            model.processing_error_code = None
            model.processing_error_detail = None
            database.flush()
            return self._record(model)

    @staticmethod
    def _candidate(model: MailMessage) -> ClassificationCandidate:
        return ClassificationCandidate(
            id=model.id,
            mail_account_id=model.mail_account_id,
            locator_folder=model.current_folder,
            uidvalidity=model.uidvalidity,
            uid=model.uid,
            subject=model.subject,
            sender=model.sender,
            recipients=tuple(model.recipients),
            body_text=model.body_text,
            body_html=model.body_html,
            attachments=tuple(
                ClassificationAttachment(
                    id=item.id,
                    filename=item.filename,
                    mime_type=item.mime_type,
                    size=item.size,
                )
                for item in model.attachments
            ),
            classification=(
                EmailClassification(model.classification) if model.classification else None
            ),
            classification_confidence=model.classification_confidence,
            classification_threshold=model.classification_threshold,
            moved_at=model.moved_at,
            status=model.status,
        )

    @staticmethod
    def _record(model: MailMessage) -> EmailClassificationRecord:
        if (
            model.classification is None
            or model.classification_confidence is None
            or model.classification_threshold is None
            or model.classification_summary is None
        ):
            raise RuntimeError("mail message does not contain a complete classification")
        return EmailClassificationRecord(
            id=model.id,
            classification=EmailClassification(model.classification),
            confidence=model.classification_confidence,
            threshold=model.classification_threshold,
            partner_name=model.partner_name,
            partner_document_id=model.partner_document_id,
            invoice_attachment_ids=tuple(UUID(value) for value in model.invoice_attachment_ids),
            supporting_attachment_ids=tuple(
                UUID(value) for value in model.supporting_attachment_ids
            ),
            summary=model.classification_summary,
            evidence=tuple(model.classification_evidence),
            status=model.status,
            current_folder=model.current_folder,
            moved_at=model.moved_at,
            error_code=model.processing_error_code,
            error_detail=model.processing_error_detail,
        )
