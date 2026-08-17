"""M13 fake-AI/PostgreSQL acceptance tests for classification, review and movement."""

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine, make_url

from app.application.services.ai import AIExecutionService, AIProviderRouter
from app.application.services.email_classification import (
    ClassificationFolders,
    EmailClassificationService,
)
from app.config import get_settings
from app.domain.email.classification import EmailClassification, EmailClassificationOutput
from app.infrastructure.ai.fake_provider import ScriptedAIProvider
from app.infrastructure.ai.prompts import PromptRepository
from app.infrastructure.persistence.models import MailAccount, MailAttachment, MailMessage
from app.infrastructure.persistence.repositories import (
    PostgreSQLAITelemetryRepository,
    PostgreSQLEmailClassificationRepository,
)
from app.infrastructure.persistence.session import create_session_factory
from app.ports.ai import AIInvalidResponseError, AIProviderError, AIResult, AIUsage
from app.ports.email import (
    EmailAttachment,
    EmailConnectionError,
    EmailMessage,
    EmailMessageLocator,
    EmailThreadContext,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 with a disposable PostgreSQL server",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPTS = PROJECT_ROOT / "app" / "infrastructure" / "ai" / "prompts"


@pytest.fixture
def database_url() -> Iterator[str]:
    configured = make_url(get_settings().database_url.get_secret_value())
    name = f"invoice_auditor_m13_{uuid4().hex}"
    admin = create_engine(
        configured.set(database="postgres").render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    value = configured.set(database=name).render_as_string(hide_password=False)
    alembic = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic.set_main_option("sqlalchemy.url", value.replace("%", "%%"))
    command.upgrade(alembic, "head")
    try:
        yield value
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    value = create_engine(database_url)
    try:
        yield value
    finally:
        value.dispose()


class FakeEmailProvider:
    def __init__(self, messages: dict[EmailMessageLocator, EmailMessage]) -> None:
        self.messages = messages
        self.moves: list[tuple[EmailMessageLocator, str]] = []
        self.fail_next_move = False

    def list_messages(self, folder: str, *, limit: int) -> tuple[EmailMessageLocator, ...]:
        return tuple(locator for locator in self.messages if locator.folder == folder)[:limit]

    def get_message(self, locator: EmailMessageLocator) -> EmailMessage:
        return self.messages[locator]

    def ensure_folder(self, folder: str) -> None:
        return None

    def move_message(self, locator: EmailMessageLocator, destination: str) -> EmailMessageLocator:
        self.moves.append((locator, destination))
        if self.fail_next_move:
            self.fail_next_move = False
            raise EmailConnectionError("temporary move failure")
        return EmailMessageLocator(destination, locator.uidvalidity + 100, locator.uid + 1000)

    def get_thread_context(
        self, locator: EmailMessageLocator, *, max_messages: int, max_characters: int
    ) -> EmailThreadContext:
        current = self.messages[locator]
        history = tuple(message for key, message in self.messages.items() if key != locator)[:1]
        return EmailThreadContext(current, history, min(max_characters, 100), False)

    def close(self) -> None:
        return None


def _message(locator: EmailMessageLocator, body: str) -> EmailMessage:
    return EmailMessage(
        locator=locator,
        raw_message=f"Subject: RE: Movimentacoes\r\n\r\n{body}".encode(),
        headers=(("X-Business-Context", "billing"),),
        message_id=f"<{locator.uid}@test>",
        in_reply_to=None,
        references=(),
        subject="RE: Movimentacoes Julho",
        sender="operations@example.test",
        recipients=("finance@example.test",),
        header_date=datetime(2026, 8, 17, tzinfo=UTC),
        received_at=datetime(2026, 8, 17, 1, tzinfo=UTC),
        body_text=body,
        body_html=None,
        attachments=(EmailAttachment("charges.csv", "text/csv", None, "attachment", b"cte,total"),),
    )


def _seed(engine: Engine, locator: EmailMessageLocator) -> tuple[UUID, UUID]:
    factory = create_session_factory(engine)
    with factory.begin() as database:
        account = MailAccount(
            display_name="test",
            host="imap.test",
            port=993,
            ssl=True,
            username=f"test-{locator.uid}@test",
        )
        database.add(account)
        database.flush()
        message = MailMessage(
            mail_account_id=account.id,
            uidvalidity=locator.uidvalidity,
            uid=locator.uid,
            subject="RE: Movimentacoes Julho",
            normalized_subject="movimentacoes julho",
            sender="operations@example.test",
            normalized_sender="operations@example.test",
            recipients=["finance@example.test"],
            headers=[],
            references=[],
            body_text="The attached list contains CT-es and invoice total.",
            normalized_body_hash=f"{locator.uid:064d}"[-64:],
            raw_size=10,
            raw_sha256=f"{locator.uid + 1:064d}"[-64:],
            raw_storage_key=f"emails/{uuid4()}",
            server_key=f"server-{uuid4()}",
            content_fingerprint=f"{uuid4().int:064x}"[-64:],
            status="INGESTED",
            original_folder=locator.folder,
            current_folder=locator.folder,
        )
        database.add(message)
        database.flush()
        attachment = MailAttachment(
            mail_message_id=message.id,
            ordinal=0,
            filename="charges.csv",
            mime_type="text/csv",
            size=9,
            sha256="a" * 64,
            storage_key=f"attachments/{uuid4()}",
        )
        database.add(attachment)
        database.flush()
        return message.id, attachment.id


def _output(confidence: str, attachment_id: UUID) -> AIResult:
    output = EmailClassificationOutput.model_validate(
        {
            "classification": "INVOICE",
            "confidence": confidence,
            "partner": {"name": "Carrier", "document_id": None},
            "invoice_attachment_ids": [str(attachment_id)],
            "supporting_attachment_ids": [],
            "summary": "Body and attachment describe a logistics invoice.",
            "evidence": ["Body mentions CT-es and invoice total."],
        }
    )
    return AIResult(output, "fake-request", AIUsage(100, 0, 20), 0, 0)


def _service(
    engine: Engine,
    provider: FakeEmailProvider,
    responses: list[AIResult | AIProviderError],
    *,
    threshold: str = "0.80",
) -> tuple[EmailClassificationService, ScriptedAIProvider]:
    factory = create_session_factory(engine)
    fake_ai = ScriptedAIProvider(responses)
    return (
        EmailClassificationService(
            repository=PostgreSQLEmailClassificationRepository(factory),
            email_provider=provider,
            ai=AIExecutionService(
                router=AIProviderRouter({"fake": fake_ai}),
                telemetry=PostgreSQLAITelemetryRepository(factory),
            ),
            prompt_provider=PromptRepository(PROMPTS),
            provider="fake",
            model="fake-luna",
            min_confidence=Decimal(threshold),
            folders=ClassificationFolders("Faturas", "Avisos", "Gerais", "Revisao"),
            thread_max_messages=10,
            thread_max_characters=50000,
        ),
        fake_ai,
    )


def test_threshold_configuration_deceptive_subject_and_idempotent_movement(engine: Engine) -> None:
    locators = [EmailMessageLocator("INBOX", 10, uid) for uid in (101, 102, 103)]
    provider = FakeEmailProvider(
        {locator: _message(locator, "Attached CT-es compose invoice 44.") for locator in locators}
    )
    seeded = [_seed(engine, locator) for locator in locators]
    service, fake_ai = _service(
        engine,
        provider,
        [
            _output(value, attachment_id)
            for value, (_, attachment_id) in zip(("0.79", "0.80", "0.81"), seeded, strict=True)
        ],
    )

    low = service.classify_and_move(seeded[0][0])
    at = service.classify_and_move(seeded[1][0])
    above = service.classify_and_move(seeded[2][0])

    assert low.classification is EmailClassification.MANUAL_REVIEW
    assert low.current_folder == "Revisao"
    assert at.classification is EmailClassification.INVOICE
    assert above.classification is EmailClassification.INVOICE
    assert {at.current_folder, above.current_folder} == {"Faturas"}
    assert {low.threshold, at.threshold, above.threshold} == {Decimal("0.8000")}
    assert "Attached CT-es" in fake_ai.calls[0][1].messages[0].content
    move_count = len(provider.moves)
    service.classify_and_move(seeded[1][0])
    assert len(fake_ai.calls) == 3
    assert len(provider.moves) == move_count


def test_configured_threshold_invalid_output_and_move_retry_preserve_original(
    engine: Engine,
) -> None:
    review_locator = EmailMessageLocator("INBOX", 20, 201)
    retry_locator = EmailMessageLocator("INBOX", 20, 202)
    invalid_locator = EmailMessageLocator("INBOX", 20, 203)
    provider = FakeEmailProvider(
        {
            review_locator: _message(review_locator, "invoice"),
            retry_locator: _message(retry_locator, "invoice"),
            invalid_locator: _message(invalid_locator, "invoice"),
        }
    )
    review = _seed(engine, review_locator)
    retry = _seed(engine, retry_locator)
    invalid = _seed(engine, invalid_locator)

    configured, _ = _service(engine, provider, [_output("0.85", review[1])], threshold="0.90")
    reviewed = configured.classify_and_move(review[0])
    assert reviewed.classification is EmailClassification.MANUAL_REVIEW
    assert reviewed.threshold == Decimal("0.9000")

    retry_service, retry_ai = _service(engine, provider, [_output("0.99", retry[1])])
    provider.fail_next_move = True
    with pytest.raises(EmailConnectionError):
        retry_service.classify_and_move(retry[0])
    recovered = retry_service.classify_and_move(retry[0])
    assert recovered.status == "MOVED"
    assert recovered.error_code is None
    assert len(retry_ai.calls) == 1
    with create_session_factory(engine)() as database:
        model = database.get(MailMessage, retry[0])
        assert model is not None
        assert model.raw_storage_key.startswith("emails/")
        assert model.original_folder == "INBOX"

    invalid_result = _output("0.99", uuid4())
    invalid_service, _ = _service(engine, provider, [invalid_result])
    with pytest.raises(AIInvalidResponseError, match="attachment IDs"):
        invalid_service.classify_and_move(invalid[0])
    with create_session_factory(engine)() as database:
        model = database.scalar(select(MailMessage).where(MailMessage.id == invalid[0]))
        assert (
            model is not None and model.classification is None and model.current_folder == "INBOX"
        )
