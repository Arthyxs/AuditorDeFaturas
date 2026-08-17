"""PostgreSQL adapters for canonical invoice intake and IMAP source projection."""

import re
import unicodedata
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select

from app.domain.intake.models import (
    InvoiceIntakeResult,
    InvoiceRecord,
    InvoiceSubmissionCommand,
    SubmissionFileInput,
    SubmissionFileRole,
    SubmissionSource,
)
from app.infrastructure.persistence.models import (
    DocumentChargeItem,
    Invoice,
    InvoiceDocument,
    InvoiceSubmission,
    MailMessage,
    Partner,
    SubmissionFile,
)
from app.infrastructure.persistence.session import SessionFactory, session_scope


def _advisory_key(value: str) -> int:
    unsigned = int.from_bytes(sha256(value.encode()).digest()[:8], "big")
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned


def _normalize_partner(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"\s+", " ", normalized)


class PostgreSQLInvoiceIntakeRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def create_or_get(self, command: InvoiceSubmissionCommand) -> InvoiceIntakeResult:
        with session_scope(self._session_factory) as database:
            for key in sorted(
                {
                    _advisory_key(f"submission-key:{command.idempotency_key}"),
                    _advisory_key(f"submission-content:{command.content_hash}"),
                }
            ):
                database.execute(select(func.pg_advisory_xact_lock(key)))
            existing = database.scalar(
                select(InvoiceSubmission).where(
                    or_(
                        InvoiceSubmission.idempotency_key == command.idempotency_key,
                        InvoiceSubmission.content_hash == command.content_hash,
                    )
                )
            )
            if existing is not None:
                if (
                    existing.idempotency_key == command.idempotency_key
                    and existing.content_hash != command.content_hash
                ):
                    raise ValueError("idempotency key was already used for different content")
                if existing.invoice is None:
                    raise RuntimeError("canonical submission exists without its invoice")
                return InvoiceIntakeResult(self._record(existing.invoice, command.source), False)

            partner_id = self._partner_id(database, command)
            submission = InvoiceSubmission(
                source_type=command.source.value,
                idempotency_key=command.idempotency_key,
                content_hash=command.content_hash,
                mail_message_id=command.mail_message_id,
                submitted_by_id=command.submitted_by_id,
                metadata_json=command.metadata.model_dump(mode="json"),
                note=command.note,
                status="ACCEPTED",
            )
            database.add(submission)
            database.flush()
            for item in command.files:
                database.add(
                    SubmissionFile(
                        submission_id=submission.id,
                        role=item.role.value,
                        ordinal=item.ordinal,
                        original_filename=item.original_filename,
                        mime_type=item.mime_type,
                        size=item.size,
                        sha256=item.sha256,
                        storage_key=item.storage_key,
                    )
                )
            metadata = command.metadata
            invoice = Invoice(
                submission_id=submission.id,
                mail_message_id=command.mail_message_id,
                partner_id=partner_id,
                partner_name_raw=metadata.partner_name,
                invoice_number=metadata.invoice_number,
                issue_date=metadata.issue_date,
                due_date=metadata.due_date,
                currency=metadata.currency,
                amount_charged=metadata.amount_charged,
                status="PROCESSING",
            )
            database.add(invoice)
            database.flush()
            for document in metadata.documents:
                document_model = InvoiceDocument(
                    invoice_id=invoice.id,
                    document_type=document.document_type,
                    document_number=document.document_number,
                    issue_date=document.issue_date,
                    origin_city=document.origin_city,
                    origin_state=document.origin_state,
                    destination_city=document.destination_city,
                    destination_state=document.destination_state,
                    origin_zip=document.origin_zip,
                    destination_zip=document.destination_zip,
                    real_weight=document.real_weight,
                    cubic_weight=document.cubic_weight,
                    chargeable_weight=document.chargeable_weight,
                    merchandise_value=document.merchandise_value,
                    amount_charged=document.amount_charged,
                    our_freight_revenue=document.our_freight_revenue,
                    source_reference=document.source_reference,
                )
                database.add(document_model)
                database.flush()
                for charge in document.charge_items:
                    database.add(
                        DocumentChargeItem(
                            invoice_document_id=document_model.id,
                            name_raw=charge.name_raw,
                            name_normalized=charge.name_normalized,
                            charged_amount=charge.charged_amount,
                        )
                    )
            database.flush()
            database.refresh(invoice, attribute_names=["documents"])
            return InvoiceIntakeResult(self._record(invoice, command.source), True)

    @staticmethod
    def _partner_id(database, command: InvoiceSubmissionCommand) -> UUID | None:  # type: ignore[no-untyped-def]
        metadata = command.metadata
        if metadata.partner_name is None and metadata.partner_document_id is None:
            return None
        name = metadata.partner_name or metadata.partner_document_id or "unknown"
        normalized = _normalize_partner(name)
        lock_values = {f"partner-name:{normalized}"}
        if metadata.partner_document_id:
            lock_values.add(f"partner-document:{metadata.partner_document_id}")
        for value in sorted(lock_values):
            database.execute(select(func.pg_advisory_xact_lock(_advisory_key(value))))
        filters = [Partner.normalized_name == normalized]
        if metadata.partner_document_id:
            filters.append(Partner.document_id == metadata.partner_document_id)
        partner_id = database.scalar(select(Partner.id).where(or_(*filters)).limit(1))
        if partner_id is None:
            partner = Partner(
                id=uuid4(),
                normalized_name=normalized,
                display_name=name,
                document_id=metadata.partner_document_id,
                aliases=[],
            )
            database.add(partner)
            database.flush()
            partner_id = partner.id
        return UUID(str(partner_id)) if partner_id is not None else None

    @staticmethod
    def _record(model: Invoice, source: SubmissionSource) -> InvoiceRecord:
        return InvoiceRecord(
            id=model.id,
            submission_id=model.submission_id,
            source=source,
            partner_id=model.partner_id,
            partner_name_raw=model.partner_name_raw,
            invoice_number=model.invoice_number,
            issue_date=model.issue_date,
            due_date=model.due_date,
            currency=model.currency,
            amount_charged=model.amount_charged,
            status=model.status,
            document_count=len(model.documents),
            created_at=model.created_at,
        )


class PostgreSQLIMAPInvoiceSourceRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def source_files(self, message_id: UUID) -> tuple[str, tuple[SubmissionFileInput, ...]]:
        with session_scope(self._session_factory) as database:
            message = database.scalar(select(MailMessage).where(MailMessage.id == message_id))
            if message is None or message.classification != "INVOICE":
                raise LookupError("classified invoice e-mail not found")
            invoice_ids = {UUID(value) for value in message.invoice_attachment_ids}
            files: list[SubmissionFileInput] = []
            raw_role = (
                SubmissionFileRole.INVOICE if not invoice_ids else SubmissionFileRole.AUXILIARY
            )
            files.append(
                SubmissionFileInput(
                    role=raw_role,
                    ordinal=0,
                    original_filename="message.eml",
                    mime_type="message/rfc822",
                    size=message.raw_size,
                    sha256=message.raw_sha256,
                    storage_key=message.raw_storage_key,
                )
            )
            for ordinal, attachment in enumerate(message.attachments, start=1):
                files.append(
                    SubmissionFileInput(
                        role=(
                            SubmissionFileRole.INVOICE
                            if attachment.id in invoice_ids
                            else SubmissionFileRole.AUXILIARY
                        ),
                        ordinal=ordinal,
                        original_filename=attachment.filename,
                        mime_type=attachment.mime_type,
                        size=attachment.size,
                        sha256=attachment.sha256,
                        storage_key=attachment.storage_key,
                    )
                )
            return message.content_fingerprint, tuple(files)
