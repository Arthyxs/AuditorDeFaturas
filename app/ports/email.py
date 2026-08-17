"""Replaceable e-mail transport contract and provider-neutral message models."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class EmailProviderError(Exception):
    """Base error exposed by e-mail providers without leaking implementation details."""


class EmailConnectionError(EmailProviderError):
    """The remote mailbox could not be reached or authenticated."""


class EmailFolderError(EmailProviderError):
    """A mailbox folder could not be selected, created or used."""


class EmailMessageNotFoundError(EmailProviderError):
    """The requested server message no longer exists at the given location."""


@dataclass(frozen=True)
class EmailMessageLocator:
    """Stable message location within one UIDVALIDITY epoch."""

    folder: str
    uidvalidity: int
    uid: int


@dataclass(frozen=True)
class EmailAttachment:
    """One decoded MIME attachment."""

    filename: str
    mime_type: str
    content_id: str | None
    disposition: str | None
    payload: bytes


@dataclass(frozen=True)
class EmailMessage:
    """Complete provider-neutral representation of an original e-mail."""

    locator: EmailMessageLocator
    raw_message: bytes
    headers: tuple[tuple[str, str], ...]
    message_id: str | None
    in_reply_to: str | None
    references: tuple[str, ...]
    subject: str
    sender: str
    recipients: tuple[str, ...]
    header_date: datetime | None
    received_at: datetime | None
    body_text: str | None
    body_html: str | None
    attachments: tuple[EmailAttachment, ...]


@dataclass(frozen=True)
class EmailThreadContext:
    """Bounded related-message context, oldest first."""

    current: EmailMessage
    history: tuple[EmailMessage, ...]
    total_characters: int
    truncated: bool


class EmailProvider(Protocol):
    """Port for mailbox operations independent of IMAP or a concrete server."""

    def list_messages(self, folder: str, *, limit: int) -> tuple[EmailMessageLocator, ...]:
        """List at most ``limit`` messages without changing their seen state."""

    def get_message(self, locator: EmailMessageLocator) -> EmailMessage:
        """Retrieve a complete original message without marking it as read."""

    def ensure_folder(self, folder: str) -> None:
        """Create the folder if it does not already exist."""

    def move_message(self, locator: EmailMessageLocator, destination: str) -> EmailMessageLocator:
        """Move one message and return its new server location when available."""

    def get_thread_context(
        self,
        locator: EmailMessageLocator,
        *,
        max_messages: int,
        max_characters: int,
    ) -> EmailThreadContext:
        """Resolve bounded context for a reply/thread."""

    def close(self) -> None:
        """Close the active provider connection, if any."""
