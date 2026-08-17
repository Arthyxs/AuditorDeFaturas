"""M11 PostgreSQL ingestion, preservation, idempotency and concurrency acceptance tests."""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine, make_url

from app.application.services.email_ingestion import EmailIngestionService
from app.config import get_settings
from app.domain.email.models import MailAccountRecord
from app.infrastructure.persistence.models import MailAttachment, MailMessage
from app.infrastructure.persistence.repositories import PostgreSQLMailIngestionRepository
from app.infrastructure.persistence.session import create_session_factory
from app.infrastructure.storage import LocalStorageProvider
from app.ports.email import (
    EmailAttachment,
    EmailMessage,
    EmailMessageLocator,
    EmailThreadContext,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 with a disposable PostgreSQL server",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def database_url() -> Iterator[str]:
    configured = make_url(get_settings().database_url.get_secret_value())
    database_name = f"invoice_auditor_m11_{uuid4().hex}"
    admin_url = configured.set(database="postgres")
    test_url = configured.set(database=database_name)
    admin = create_engine(
        admin_url.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    value = test_url.render_as_string(hide_password=False)
    alembic = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic.set_main_option("sqlalchemy.url", value.replace("%", "%%"))
    command.upgrade(alembic, "head")
    try:
        yield value
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    value = create_engine(database_url)
    try:
        yield value
    finally:
        value.dispose()


class FakeProvider:
    def __init__(self, messages: dict[EmailMessageLocator, EmailMessage]) -> None:
        self.messages = messages

    def list_messages(self, folder: str, *, limit: int) -> tuple[EmailMessageLocator, ...]:
        return tuple(locator for locator in self.messages if locator.folder == folder)[-limit:]

    def get_message(self, locator: EmailMessageLocator) -> EmailMessage:
        return self.messages[locator]

    def ensure_folder(self, folder: str) -> None:
        return None

    def move_message(self, locator: EmailMessageLocator, destination: str) -> EmailMessageLocator:
        raise NotImplementedError

    def get_thread_context(
        self,
        locator: EmailMessageLocator,
        *,
        max_messages: int,
        max_characters: int,
    ) -> EmailThreadContext:
        raise NotImplementedError

    def close(self) -> None:
        return None


def _message(locator: EmailMessageLocator, *, reverse_attachments: bool = False) -> EmailMessage:
    attachments: tuple[EmailAttachment, ...] = (
        EmailAttachment("invoice.csv", "text/csv", None, "attachment", b"invoice-data"),
        EmailAttachment("note.txt", "text/plain", None, "attachment", b"supporting-note"),
    )
    if reverse_attachments:
        attachments = tuple(reversed(attachments))
    return EmailMessage(
        locator=locator,
        raw_message=b"From: billing@example.com\r\nMessage-ID: <same@example.com>\r\n\r\nbody",
        headers=(("From", "billing@example.com"), ("Message-ID", "<same@example.com>")),
        message_id="<same@example.com>",
        in_reply_to=None,
        references=(),
        subject="Invoice August",
        sender="billing@example.com",
        recipients=("finance@example.com",),
        header_date=datetime(2026, 8, 17, 12, tzinfo=UTC),
        received_at=datetime(2026, 8, 17, 12, 1, tzinfo=UTC),
        body_text="Invoice body",
        body_html=None,
        attachments=attachments,
    )


def _account(engine: Engine) -> MailAccountRecord:
    factory = create_session_factory(engine)
    repository = PostgreSQLMailIngestionRepository(factory)
    first = repository.get_or_create_account(
        display_name="Test mailbox",
        host="IMAP.TEST",
        port=993,
        ssl=True,
        username="TEST@example.com",
    )
    second = repository.get_or_create_account(
        display_name="Updated test mailbox",
        host="imap.test",
        port=993,
        ssl=True,
        username="test@example.com",
    )
    assert second.id == first.id
    assert second.display_name == "Updated test mailbox"
    return second


def _service(engine: Engine, storage_root: Path, provider: FakeProvider) -> EmailIngestionService:
    factory = create_session_factory(engine)
    return EmailIngestionService(
        email_provider=provider,
        storage=LocalStorageProvider(storage_root, max_upload_size_bytes=1024 * 1024),
        repository=PostgreSQLMailIngestionRepository(factory),
    )


def _object_count(root: Path, area: str) -> int:
    location = root / area
    if not location.exists():
        return 0
    return len([item for item in location.iterdir() if item.name != ".staging"])


def test_repeat_uid_and_move_content_do_not_duplicate_originals(
    engine: Engine, tmp_path: Path
) -> None:
    account = _account(engine)
    inbox = EmailMessageLocator("INBOX", 10, 100)
    moved = EmailMessageLocator("Processed", 20, 900)
    provider = FakeProvider(
        {
            inbox: _message(inbox),
            moved: _message(moved, reverse_attachments=True),
        }
    )
    service = _service(engine, tmp_path, provider)

    first = service.ingest(mail_account_id=account.id, locator=inbox)
    same_uid = service.ingest(mail_account_id=account.id, locator=inbox)
    after_move = service.ingest(mail_account_id=account.id, locator=moved)

    assert first.created is True
    assert same_uid.created is False
    assert same_uid.duplicate_reason == "server_key"
    assert after_move.created is False
    assert after_move.duplicate_reason == "content_fingerprint"
    assert {first.message.id, same_uid.message.id, after_move.message.id} == {first.message.id}
    assert _object_count(tmp_path, "emails") == 1
    assert _object_count(tmp_path, "attachments") == 2

    with create_session_factory(engine)() as database:
        assert database.scalar(select(func.count()).select_from(MailMessage)) == 1
        assert database.scalar(select(func.count()).select_from(MailAttachment)) == 2
        persisted = database.scalar(select(MailMessage))
        assert persisted is not None
        assert persisted.original_folder == "INBOX"
        assert persisted.current_folder == "INBOX"

    storage = LocalStorageProvider(tmp_path, max_upload_size_bytes=1024 * 1024)
    with storage.open_read(first.message.raw_storage_key) as original:
        raw = original.read()
    assert raw == provider.messages[inbox].raw_message
    assert first.message.raw_sha256 == storage.metadata(first.message.raw_storage_key).sha256


def test_concurrent_ingestion_creates_one_message_attachment_set_and_blob_set(
    engine: Engine, tmp_path: Path
) -> None:
    account = _account(engine)
    first_locator = EmailMessageLocator("INBOX", 10, 101)
    moved_locator = EmailMessageLocator("Processed", 20, 901)
    provider = FakeProvider(
        {
            first_locator: _message(first_locator),
            moved_locator: _message(moved_locator, reverse_attachments=True),
        }
    )
    service = _service(engine, tmp_path, provider)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda locator: service.ingest(mail_account_id=account.id, locator=locator),
                (first_locator, moved_locator),
            )
        )

    assert sorted(result.created for result in results) == [False, True]
    assert len({result.message.id for result in results}) == 1
    assert _object_count(tmp_path, "emails") == 1
    assert _object_count(tmp_path, "attachments") == 2
    with create_session_factory(engine)() as database:
        assert database.scalar(select(func.count()).select_from(MailMessage)) == 1
        assert database.scalar(select(func.count()).select_from(MailAttachment)) == 2
