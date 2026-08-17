"""M14 manual/IMAP canonical invoice intake acceptance tests."""

import io
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.application.services.invoice_intake import IMAPInvoiceIntakeAdapter, InvoiceIntakeService
from app.config import Settings, get_settings
from app.infrastructure.persistence.models import (
    Invoice,
    InvoiceDocument,
    InvoiceSubmission,
    MailAccount,
    MailAttachment,
    MailMessage,
    Partner,
    ProcessingJob,
    SubmissionFile,
    User,
    UserRole,
)
from app.infrastructure.persistence.repositories import PostgreSQLJobQueue
from app.infrastructure.persistence.repositories.invoice_intake import (
    PostgreSQLIMAPInvoiceSourceRepository,
    PostgreSQLInvoiceIntakeRepository,
)
from app.infrastructure.persistence.session import create_session_factory
from app.infrastructure.security.passwords import hash_password
from app.main import create_app
from app.worker.jobs.invoice_intake import TARIFF_SELECTION_JOB

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 with a disposable PostgreSQL server",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "https://invoice-auditor.test"
PASSWORD = "test-only-password-123"


def _pdf() -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)
    return output.getvalue()


@pytest.fixture
def database_url() -> Iterator[str]:
    configured = make_url(get_settings().database_url.get_secret_value())
    name = f"invoice_auditor_m14_{uuid4().hex}"
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


def _settings(database_url: str, storage_root: Path) -> Settings:
    return Settings.model_validate(
        {
            "app_env": "test",
            "app_base_url": ORIGIN,
            "app_secret_key": "test-app-secret-000000000000000000000000000",
            "first_admin_bootstrap_token": "test-bootstrap-token-000000000000000000000000",
            "postgres_password": "test-postgres-secret-00000000000000000000000",
            "database_url": database_url,
            "storage_root": storage_root,
        }
    )


def _app(database_url: str, storage_root: Path):  # type: ignore[no-untyped-def]
    application = create_app(_settings(database_url, storage_root))
    with create_session_factory(application.state.database_engine)() as database:
        for role in UserRole:
            database.add(
                User(
                    username=role.value.casefold(),
                    password_hash=hash_password(PASSWORD),
                    role=role,
                    is_active=True,
                )
            )
        database.commit()
    return application


def _login(client: TestClient, role: UserRole) -> None:
    response = client.post(
        "/api/auth/login",
        headers={"Origin": ORIGIN},
        json={"username": role.value.casefold(), "password": PASSWORD},
    )
    assert response.status_code == 200


def _manual(client: TestClient, metadata: dict[str, object], content: bytes | None = None):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/invoices/manual",
        headers={"Origin": ORIGIN},
        files={"invoice": ("invoice.pdf", content or _pdf(), "application/pdf")},
        data={"metadata": json.dumps(metadata), "note": "manual acceptance"},
    )


def test_manual_intake_rbac_idempotency_decimals_nulls_and_hundreds_of_documents(
    database_url: str, tmp_path: Path
) -> None:
    application = _app(database_url, tmp_path)
    documents = [
        {
            "document_type": "CTE",
            "document_number": str(index),
            "amount_charged": "10.123456",
            "real_weight": "5.25",
            "charge_items": [{"name_raw": "Frete", "charged_amount": "10.123456"}],
        }
        for index in range(250)
    ]
    metadata: dict[str, object] = {
        "partner_name": "Transportadora Exemplo",
        "invoice_number": "F-14",
        "currency": "brl",
        "amount_charged": "2530.864000",
        "documents": documents,
    }
    with TestClient(application, base_url=ORIGIN) as viewer:
        _login(viewer, UserRole.VIEWER)
        assert _manual(viewer, metadata).status_code == 403

    with TestClient(application, base_url=ORIGIN) as operator:
        _login(operator, UserRole.OPERATOR)
        first = _manual(operator, metadata)
        assert first.status_code == 201, first.text
        payload = first.json()
        assert payload["created"] is True
        assert payload["invoice"]["source"] == "MANUAL"
        assert payload["invoice"]["document_count"] == 250
        assert payload["invoice"]["amount_charged"] == "2530.864000"
        assert payload["invoice"]["due_date"] is None
        second = _manual(operator, metadata)
        assert second.status_code == 201 and second.json()["created"] is False
        assert second.json()["invoice"]["id"] == payload["invoice"]["id"]
        invalid_money = _manual(operator, {"amount_charged": 1.25})
        assert invalid_money.status_code == 422
        known_partner = _manual(
            operator,
            {"partner_name": "  TRANSPORTADORA   EXEMPLO ", "invoice_number": "F-15"},
        )
        assert known_partner.status_code == 201 and known_partner.json()["created"] is True
        assert known_partner.json()["invoice"]["partner_id"] == payload["invoice"]["partner_id"]

    factory = create_session_factory(application.state.database_engine)
    with factory() as database:
        assert database.scalar(select(func.count()).select_from(InvoiceSubmission)) == 2
        assert database.scalar(select(func.count()).select_from(Invoice)) == 2
        assert database.scalar(select(func.count()).select_from(InvoiceDocument)) == 250
        assert database.scalar(select(func.count()).select_from(Partner)) == 1
        assert database.scalar(select(func.count()).select_from(SubmissionFile)) == 2
        jobs = database.scalars(select(ProcessingJob)).all()
        assert len(jobs) == 2 and {job.job_type for job in jobs} == {TARIFF_SELECTION_JOB}
    assert len(application.state.storage_provider.list_files("invoices")) == 2

    database = factory()
    try:
        user_id = database.scalar(select(User.id).limit(1))
        database.add(
            InvoiceSubmission(
                source_type="IMAP",
                idempotency_key=f"invalid-{uuid4()}",
                content_hash=uuid4().hex + uuid4().hex,
                mail_message_id=None,
                submitted_by_id=user_id,
                metadata_json={},
                status="ACCEPTED",
            )
        )
        with pytest.raises(IntegrityError):
            database.flush()
        database.rollback()
    finally:
        database.close()
    application.state.database_engine.dispose()


def test_imap_and_manual_channels_create_traceable_invoices_and_same_downstream_job(
    database_url: str, tmp_path: Path
) -> None:
    application = _app(database_url, tmp_path)
    with TestClient(application, base_url=ORIGIN) as operator:
        _login(operator, UserRole.OPERATOR)
        manual = _manual(operator, {})
        assert manual.status_code == 201

    storage = application.state.storage_provider
    raw = storage.store_original("emails", "message.eml", "message/rfc822", io.BytesIO(b"raw"))
    attachment = storage.store_original(
        "attachments", "invoice.csv", "text/csv", io.BytesIO(b"cte,total\n1,10")
    )
    factory = create_session_factory(application.state.database_engine)
    with factory.begin() as database:
        account = MailAccount(
            display_name="test", host="imap.test", port=993, ssl=True, username="test@test"
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
            raw_size=raw.size,
            raw_sha256=raw.sha256,
            raw_storage_key=raw.key,
            server_key=f"server-{uuid4()}",
            content_fingerprint="b" * 64,
            status="MOVED",
            original_folder="INBOX",
            current_folder="Faturas",
            classification="INVOICE",
            classification_confidence="0.9900",
            classification_threshold="0.8000",
            partner_name="Carrier From Mail",
            invoice_attachment_ids=[],
            classification_summary="Invoice",
            classification_evidence=["Attachment"],
            classified_at=datetime.now(UTC),
            moved_at=datetime.now(UTC),
        )
        database.add(message)
        database.flush()
        attached = MailAttachment(
            mail_message_id=message.id,
            ordinal=0,
            filename="invoice.csv",
            mime_type="text/csv",
            size=attachment.size,
            sha256=attachment.sha256,
            storage_key=attachment.key,
        )
        database.add(attached)
        database.flush()
        message.invoice_attachment_ids = [str(attached.id)]
        message_id = message.id

    adapter = IMAPInvoiceIntakeAdapter(
        source_repository=PostgreSQLIMAPInvoiceSourceRepository(factory),
        intake=InvoiceIntakeService(
            repository=PostgreSQLInvoiceIntakeRepository(factory),
            queue=PostgreSQLJobQueue(factory),
            max_attempts=5,
        ),
    )
    first = adapter.submit_invoice_email(
        message_id, partner_name="Carrier From Mail", partner_document_id=None
    )
    repeated = adapter.submit_invoice_email(
        message_id, partner_name="Carrier From Mail", partner_document_id=None
    )
    assert first.created is True and repeated.created is False
    assert repeated.invoice.id == first.invoice.id

    with factory() as database:
        submissions = database.scalars(
            select(InvoiceSubmission).order_by(InvoiceSubmission.created_at)
        ).all()
        assert {item.source_type for item in submissions} == {"MANUAL", "IMAP"}
        assert submissions[1].mail_message_id == message_id
        assert submissions[0].submitted_by_id is not None
        jobs = database.scalars(select(ProcessingJob).order_by(ProcessingJob.created_at)).all()
        assert len(jobs) == 2
        assert {job.job_type for job in jobs} == {TARIFF_SELECTION_JOB}
        assert all(set(job.payload) == {"invoice_id"} for job in jobs)
    application.state.database_engine.dispose()
