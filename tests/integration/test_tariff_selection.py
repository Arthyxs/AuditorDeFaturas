"""M15 fake-AI/PostgreSQL semantic tariff-selection acceptance tests."""

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine, make_url

from app.application.services.ai import AIExecutionService, AIProviderRouter
from app.application.services.tariff_selection import TariffSelectionService
from app.config import get_settings
from app.domain.tariffs.selection import TariffSelectionOutput, TariffSelectionStatus
from app.infrastructure.ai.fake_provider import ScriptedAIProvider
from app.infrastructure.ai.prompts import PromptRepository
from app.infrastructure.persistence.models import (
    Invoice,
    InvoiceDocument,
    InvoiceSubmission,
    MailAccount,
    MailMessage,
    PendingItem,
    TariffFile,
    TariffSelectionRun,
    User,
    UserRole,
)
from app.infrastructure.persistence.repositories import PostgreSQLAITelemetryRepository
from app.infrastructure.persistence.repositories.tariff_selection import (
    PostgreSQLTariffSelectionRepository,
)
from app.infrastructure.persistence.session import create_session_factory
from app.ports.ai import AIInvalidResponseError, AIProviderError, AIResult, AIUsage

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 with a disposable PostgreSQL server",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPTS = PROJECT_ROOT / "app" / "infrastructure" / "ai" / "prompts"


@pytest.fixture
def database_url() -> Iterator[str]:
    configured = make_url(get_settings().database_url.get_secret_value())
    name = f"invoice_auditor_m15_{uuid4().hex}"
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


def _user(engine: Engine) -> UUID:
    factory = create_session_factory(engine)
    with factory.begin() as database:
        user = User(
            username=f"operator-{uuid4()}",
            password_hash="test-hash",
            role=UserRole.OPERATOR,
            is_active=True,
        )
        database.add(user)
        database.flush()
        return user.id


def _invoice(engine: Engine, *, source: str = "MANUAL", user_id: UUID | None = None) -> UUID:
    factory = create_session_factory(engine)
    with factory.begin() as database:
        mail_message_id = None
        if source == "IMAP":
            account = MailAccount(
                display_name="test",
                host=f"imap-{uuid4()}.test",
                port=993,
                ssl=True,
                username=f"test-{uuid4()}@test",
            )
            database.add(account)
            database.flush()
            message = MailMessage(
                mail_account_id=account.id,
                uidvalidity=1,
                uid=1,
                subject="invoice",
                normalized_subject="invoice",
                sender="carrier@test",
                normalized_sender="carrier@test",
                recipients=["finance@test"],
                headers=[],
                references=[],
                normalized_body_hash="a" * 64,
                raw_size=3,
                raw_sha256=uuid4().hex + uuid4().hex,
                raw_storage_key=f"emails/{uuid4()}",
                server_key=f"server-{uuid4()}",
                content_fingerprint=uuid4().hex + uuid4().hex,
                status="MOVED",
                original_folder="INBOX",
                current_folder="Faturas",
                classification="INVOICE",
                classification_confidence=Decimal("0.99"),
                classification_threshold=Decimal("0.80"),
                classification_summary="invoice",
                classification_evidence=["body"],
            )
            database.add(message)
            database.flush()
            mail_message_id = message.id
        submission = InvoiceSubmission(
            source_type=source,
            idempotency_key=f"{source.casefold()}:{uuid4()}",
            content_hash=uuid4().hex + uuid4().hex,
            mail_message_id=mail_message_id,
            submitted_by_id=user_id if source == "MANUAL" else None,
            metadata_json={},
            status="ACCEPTED",
        )
        database.add(submission)
        database.flush()
        invoice = Invoice(
            submission_id=submission.id,
            mail_message_id=mail_message_id,
            partner_name_raw="Carrier X",
            invoice_number="INV-2026",
            issue_date=datetime(2026, 8, 1, tzinfo=UTC).date(),
            currency="BRL",
            amount_charged=Decimal("100.00"),
            status="PROCESSING",
        )
        database.add(invoice)
        database.flush()
        database.add(
            InvoiceDocument(
                invoice_id=invoice.id,
                document_type="CTE",
                document_number="123",
                origin_city="Ipatinga",
                origin_state="MG",
                destination_city="Sao Paulo",
                destination_state="SP",
                amount_charged=Decimal("100.00"),
                source_reference={"file": "invoice.pdf", "page": 1},
            )
        )
        return invoice.id


def _tariff(engine: Engine, user_id: UUID, name: str, *, active: bool = True) -> TariffFile:
    factory = create_session_factory(engine)
    with factory.begin() as database:
        item = TariffFile(
            original_filename=name,
            internal_filename=f"{uuid4()}.pdf",
            extension="pdf",
            mime_type="application/pdf",
            size=10,
            sha256=uuid4().hex + uuid4().hex,
            storage_key=f"tariffs/{uuid4()}",
            description=f"Tariff for {name}",
            active=active,
            version=1,
            version_group_id=uuid4(),
            uploaded_by_id=user_id,
        )
        database.add(item)
        database.flush()
        database.expunge(item)
        return item


def _result(ids: list[UUID], confidence: str = "0.95") -> AIResult:
    output = TariffSelectionOutput.model_validate(
        {
            "selected_tariff_ids": [str(value) for value in ids],
            "confidence": confidence,
            "reason": "Partner, date and route metadata match the selected tariff files.",
        }
    )
    return AIResult(output, "fake-selection", AIUsage(100, 10, 20), 0, 0)


def _service(
    engine: Engine,
    responses: list[AIResult | AIProviderError],
    *,
    threshold: str = "0.80",
) -> tuple[TariffSelectionService, ScriptedAIProvider, PostgreSQLTariffSelectionRepository]:
    factory = create_session_factory(engine)
    fake = ScriptedAIProvider(responses)
    repository = PostgreSQLTariffSelectionRepository(factory)
    return (
        TariffSelectionService(
            repository=repository,
            ai=AIExecutionService(
                router=AIProviderRouter({"fake": fake}),
                telemetry=PostgreSQLAITelemetryRepository(factory),
            ),
            prompt_provider=PromptRepository(PROMPTS),
            provider="fake",
            model="fake-terra",
            min_confidence=Decimal(threshold),
        ),
        fake,
        repository,
    )


def test_zero_candidates_creates_explicit_pending_without_ai(engine: Engine) -> None:
    user_id = _user(engine)
    invoice_id = _invoice(engine, user_id=user_id)
    service, fake, repository = _service(engine, [])
    result = service.select(invoice_id)
    assert result.status is TariffSelectionStatus.NO_TARIFF
    assert result.selected_tariff_ids == () and result.ai_call_id is None
    assert fake.calls == [] and repository.selected_storage_keys(invoice_id) == ()
    with create_session_factory(engine)() as database:
        invoice = database.get(Invoice, invoice_id)
        pending = database.scalar(select(PendingItem).where(PendingItem.invoice_id == invoice_id))
        assert invoice is not None and invoice.status == "PENDING"
        assert pending is not None and pending.type == "PENDING_NO_TARIFF"


def test_one_and_multiple_candidates_persist_only_exact_active_selection(engine: Engine) -> None:
    user_id = _user(engine)
    invoice_id = _invoice(engine, user_id=user_id)
    first = _tariff(engine, user_id, "carrier-base.pdf")
    second = _tariff(engine, user_id, "carrier-cities.pdf")
    inactive = _tariff(engine, user_id, "old.pdf", active=False)
    service, fake, repository = _service(engine, [_result([first.id, second.id])])
    selected = service.select(invoice_id)
    repeated = service.select(invoice_id)
    assert selected.status is TariffSelectionStatus.SELECTED
    assert set(selected.selected_tariff_ids) == {first.id, second.id}
    assert repeated == selected and len(fake.calls) == 1
    prompt_payload = json.loads(fake.calls[0][1].messages[0].content)
    assert {item["id"] for item in prompt_payload["active_tariff_catalog"]} == {
        str(first.id),
        str(second.id),
    }
    assert str(inactive.id) not in fake.calls[0][1].messages[0].content
    assert set(repository.selected_storage_keys(invoice_id)) == {
        first.storage_key,
        second.storage_key,
    }


def test_invalid_id_and_low_confidence_never_link_tariffs_as_authoritative(engine: Engine) -> None:
    user_id = _user(engine)
    invalid_invoice = _invoice(engine, user_id=user_id)
    low_invoice = _invoice(engine, user_id=user_id)
    tariff = _tariff(engine, user_id, "carrier.pdf")
    invalid_service, _, invalid_repository = _service(engine, [_result([uuid4()])])
    with pytest.raises(AIInvalidResponseError, match="unknown ID"):
        invalid_service.select(invalid_invoice)
    assert invalid_repository.existing(invalid_invoice) is None

    low_service, _, low_repository = _service(
        engine, [_result([tariff.id], "0.79")], threshold="0.80"
    )
    low = low_service.select(low_invoice)
    assert low.status is TariffSelectionStatus.LOW_CONFIDENCE
    assert low.selected_tariff_ids == ()
    assert low_repository.selected_storage_keys(low_invoice) == ()
    with create_session_factory(engine)() as database:
        pending = database.scalar(select(PendingItem).where(PendingItem.invoice_id == low_invoice))
        assert pending is not None and "LOW_CONFIDENCE" in pending.type


def test_equivalent_imap_and_manual_invoices_send_source_neutral_context(engine: Engine) -> None:
    user_id = _user(engine)
    manual_id = _invoice(engine, source="MANUAL", user_id=user_id)
    imap_id = _invoice(engine, source="IMAP")
    tariff = _tariff(engine, user_id, "carrier.pdf")
    service, fake, _ = _service(engine, [_result([tariff.id]), _result([tariff.id])])
    manual = service.select(manual_id)
    imap = service.select(imap_id)
    assert manual.status is imap.status is TariffSelectionStatus.SELECTED
    assert manual.selected_tariff_ids == imap.selected_tariff_ids == (tariff.id,)
    assert fake.calls[0][1].messages[0].content == fake.calls[1][1].messages[0].content
    with create_session_factory(engine)() as database:
        assert database.scalar(select(func.count()).select_from(TariffSelectionRun)) == 2
