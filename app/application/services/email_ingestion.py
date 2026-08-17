"""Canonical exactly-once e-mail ingestion use case."""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import UUID

from app.domain.email.fingerprint import build_server_key, fingerprint_message
from app.domain.email.models import (
    EmailIngestionResult,
    NewMailAttachment,
    NewMailMessage,
)
from app.ports.email import EmailMessageLocator, EmailProvider
from app.ports.email_ingestion import MailIngestionRepository
from app.ports.storage import PhysicalDeletionApproval, StorageProvider


class EmailIngestionService:
    """Fetch, fingerprint and preserve one e-mail behind transactional deduplication guards."""

    def __init__(
        self,
        *,
        email_provider: EmailProvider,
        storage: StorageProvider,
        repository: MailIngestionRepository,
    ) -> None:
        self._email_provider = email_provider
        self._storage = storage
        self._repository = repository

    def ingest(
        self, *, mail_account_id: UUID, locator: EmailMessageLocator
    ) -> EmailIngestionResult:
        message = self._email_provider.get_message(locator)
        fingerprint = fingerprint_message(message)
        server_key = build_server_key(
            mail_account_id,
            uidvalidity=locator.uidvalidity,
            uid=locator.uid,
        )
        stored_keys: list[str] = []
        retained = False
        try:
            raw_stored = self._storage.store_original(
                "emails",
                f"message-{locator.uid}.eml",
                "message/rfc822",
                BytesIO(message.raw_message),
            )
            stored_keys.append(raw_stored.key)
            if raw_stored.sha256 != sha256(message.raw_message).hexdigest():
                raise RuntimeError("stored raw e-mail digest changed during ingestion")
            attachments: list[NewMailAttachment] = []
            for ordinal, attachment in enumerate(message.attachments):
                stored = self._storage.store_original(
                    "attachments",
                    self._safe_attachment_name(attachment.filename, ordinal),
                    attachment.mime_type,
                    BytesIO(attachment.payload),
                )
                stored_keys.append(stored.key)
                if stored.sha256 != sha256(attachment.payload).hexdigest():
                    raise RuntimeError("stored attachment digest changed during ingestion")
                attachments.append(
                    NewMailAttachment(
                        ordinal=ordinal,
                        filename=attachment.filename,
                        mime_type=attachment.mime_type,
                        content_id=attachment.content_id,
                        size=stored.size,
                        sha256=stored.sha256,
                        storage_key=stored.key,
                    )
                )

            with self._repository.begin_guarded(
                server_key=server_key,
                content_fingerprint=fingerprint.content_fingerprint,
            ) as transaction:
                duplicate = transaction.find_duplicate(
                    server_key=server_key,
                    content_fingerprint=fingerprint.content_fingerprint,
                )
                if duplicate is not None:
                    existing, reason = duplicate
                    result = EmailIngestionResult(
                        message=existing,
                        created=False,
                        duplicate_reason=reason,
                    )
                else:
                    record = transaction.insert(
                        NewMailMessage(
                            mail_account_id=mail_account_id,
                            uidvalidity=locator.uidvalidity,
                            uid=locator.uid,
                            message_id=message.message_id,
                            in_reply_to=message.in_reply_to,
                            references=message.references,
                            subject=message.subject,
                            normalized_subject=fingerprint.subject_normalized,
                            sender=message.sender,
                            normalized_sender=fingerprint.sender_normalized,
                            recipients=message.recipients,
                            headers=message.headers,
                            header_date=message.header_date,
                            received_at=message.received_at,
                            body_text=message.body_text,
                            body_html=message.body_html,
                            normalized_body_hash=fingerprint.normalized_body_hash,
                            raw_size=raw_stored.size,
                            raw_sha256=raw_stored.sha256,
                            raw_storage_key=raw_stored.key,
                            server_key=server_key,
                            content_fingerprint=fingerprint.content_fingerprint,
                            original_folder=locator.folder,
                            current_folder=locator.folder,
                            attachments=tuple(attachments),
                        )
                    )
                    result = EmailIngestionResult(
                        message=record, created=True, duplicate_reason=None
                    )
            retained = result.created
            return result
        finally:
            if not retained:
                self._delete_unreferenced(stored_keys)

    def _delete_unreferenced(self, keys: list[str]) -> None:
        approval = PhysicalDeletionApproval(
            reason="compensate unreferenced e-mail ingestion upload",
            references_checked=True,
        )
        for key in reversed(keys):
            self._storage.delete(key, approval=approval)

    @staticmethod
    def _safe_attachment_name(filename: str, ordinal: int) -> str:
        """Keep safe original names; use a deterministic opaque name for unsafe MIME metadata."""
        candidate = filename.strip()
        if (
            candidate
            and len(candidate) <= 255
            and candidate == Path(candidate).name
            and not any(character in candidate for character in ("/", "\\", ":"))
            and not any(ord(character) < 32 or ord(character) == 127 for character in candidate)
        ):
            return candidate
        return f"attachment-{ordinal}.bin"
