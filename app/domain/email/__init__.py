"""E-mail domain identity, normalization and records."""

from app.domain.email.fingerprint import build_server_key, fingerprint_message
from app.domain.email.models import EmailIngestionResult, MailAccountRecord, MailMessageRecord

__all__ = [
    "EmailIngestionResult",
    "MailAccountRecord",
    "MailMessageRecord",
    "build_server_key",
    "fingerprint_message",
]
