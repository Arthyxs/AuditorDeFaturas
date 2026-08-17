"""Persistence boundary for atomic e-mail ingestion and deduplication."""

from contextlib import AbstractContextManager
from typing import Protocol

from app.domain.email.models import MailAccountRecord, MailMessageRecord, NewMailMessage


class MailIngestionTransaction(Protocol):
    """Operations available while both deduplication keys are transactionally guarded."""

    def find_duplicate(
        self, *, server_key: str, content_fingerprint: str
    ) -> tuple[MailMessageRecord, str] | None:
        """Return an existing message and the matching key name."""

    def insert(self, message: NewMailMessage) -> MailMessageRecord:
        """Persist one message and all attachment references atomically."""


class MailIngestionRepository(Protocol):
    """Open a PostgreSQL-independent deduplication transaction."""

    def get_or_create_account(
        self,
        *,
        display_name: str,
        host: str,
        port: int,
        ssl: bool,
        username: str,
        active: bool = True,
    ) -> MailAccountRecord:
        """Persist non-secret mailbox configuration idempotently."""

    def begin_guarded(
        self, *, server_key: str, content_fingerprint: str
    ) -> AbstractContextManager[MailIngestionTransaction]:
        """Serialize competing ingestions for both unique identities."""
