"""Provider-neutral e-mail ingestion records."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class MailAccountRecord:
    id: UUID
    display_name: str
    host: str
    port: int
    ssl: bool
    username: str
    active: bool


@dataclass(frozen=True)
class NewMailAttachment:
    ordinal: int
    filename: str
    mime_type: str
    content_id: str | None
    size: int
    sha256: str
    storage_key: str


@dataclass(frozen=True)
class NewMailMessage:
    mail_account_id: UUID
    uidvalidity: int
    uid: int
    message_id: str | None
    in_reply_to: str | None
    references: tuple[str, ...]
    subject: str
    normalized_subject: str
    sender: str
    normalized_sender: str
    recipients: tuple[str, ...]
    headers: tuple[tuple[str, str], ...]
    header_date: datetime | None
    received_at: datetime | None
    body_text: str | None
    body_html: str | None
    normalized_body_hash: str
    raw_size: int
    raw_sha256: str
    raw_storage_key: str
    server_key: str
    content_fingerprint: str
    original_folder: str
    current_folder: str
    attachments: tuple[NewMailAttachment, ...]


@dataclass(frozen=True)
class MailMessageRecord:
    id: UUID
    mail_account_id: UUID
    server_key: str
    content_fingerprint: str
    raw_sha256: str
    raw_storage_key: str
    attachment_count: int
    created_at: datetime


@dataclass(frozen=True)
class EmailIngestionResult:
    message: MailMessageRecord
    created: bool
    duplicate_reason: str | None
