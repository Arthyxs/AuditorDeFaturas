"""Canonical, folder-independent e-mail identity and fingerprint vectors."""

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parseaddr
from hashlib import sha256
from uuid import UUID

from app.ports.email import EmailMessage

_REPLY_PREFIX = re.compile(r"^(?:(?:re|fw|fwd|enc|res)\s*:\s*)+", re.IGNORECASE)


def normalize_text(value: str | None) -> str:
    """Normalize Unicode, line endings and trailing whitespace deterministically."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in normalized.split("\n")).strip()


def normalize_sender(value: str) -> str:
    """Prefer a case-folded address while preserving a normalized fallback."""
    _, address = parseaddr(value)
    return unicodedata.normalize("NFKC", address or value).strip().casefold()


def normalize_subject(value: str) -> str:
    """Normalize reply/forward transport prefixes and Unicode deterministically."""
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return " ".join(_REPLY_PREFIX.sub("", normalized).split())


def normalize_message_id(value: str | None) -> str | None:
    """Canonicalize optional RFC message identifiers."""
    if not value:
        return None
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return normalized or None


def canonical_datetime(value: datetime | None) -> str | None:
    """Serialize aware instants in UTC; retain naive values as explicitly ambiguous."""
    if value is None:
        return None
    if value.tzinfo is None:
        return f"naive:{value.isoformat(timespec='microseconds')}"
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_json_sha256(value: object) -> str:
    """Hash canonical UTF-8 JSON."""
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


@dataclass(frozen=True)
class EmailFingerprint:
    """Normalized components and final canonical content digest."""

    sender_normalized: str
    subject_normalized: str
    message_id_normalized: str | None
    normalized_body_hash: str
    attachment_sha256s: tuple[str, ...]
    content_fingerprint: str


def build_server_key(mail_account_id: UUID, *, uidvalidity: int, uid: int) -> str:
    """Build folder-independent server identity for one account UID epoch."""
    if uidvalidity < 1 or uid < 1:
        raise ValueError("UIDVALIDITY and UID must be positive")
    return f"{mail_account_id}:{uidvalidity}:{uid}"


def fingerprint_message(message: EmailMessage) -> EmailFingerprint:
    """Calculate the approved canonical content fingerprint independent of MIME part order."""
    sender = normalize_sender(message.sender)
    subject = normalize_subject(message.subject)
    message_id = normalize_message_id(message.message_id)
    body_hash = canonical_json_sha256(
        {
            "html": normalize_text(message.body_html),
            "text": normalize_text(message.body_text),
        }
    )
    attachments = tuple(sorted(sha256(item.payload).hexdigest() for item in message.attachments))
    canonical = {
        "sender_normalized": sender,
        "subject_normalized": subject,
        "header_date": canonical_datetime(message.header_date),
        "received_at": canonical_datetime(message.received_at),
        "message_id_if_available": message_id,
        "normalized_body_hash": body_hash,
        "sorted_attachment_sha256_list": attachments,
    }
    return EmailFingerprint(
        sender_normalized=sender,
        subject_normalized=subject,
        message_id_normalized=message_id,
        normalized_body_hash=body_hash,
        attachment_sha256s=attachments,
        content_fingerprint=canonical_json_sha256(canonical),
    )
