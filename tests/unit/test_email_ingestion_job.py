"""M11 durable e-mail ingestion job payload contract."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.domain.email.models import EmailIngestionResult, MailMessageRecord
from app.domain.jobs import JobRecord, JobStatus
from app.ports.email import EmailMessageLocator
from app.worker.jobs.email_ingestion import EMAIL_INGESTION_JOB, EmailIngestionJobHandler


class FakeIngestor:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, EmailMessageLocator]] = []

    def ingest(
        self, *, mail_account_id: UUID, locator: EmailMessageLocator
    ) -> EmailIngestionResult:
        self.calls.append((mail_account_id, locator))
        return EmailIngestionResult(
            message=MailMessageRecord(
                id=uuid4(),
                mail_account_id=mail_account_id,
                server_key="server",
                content_fingerprint="a" * 64,
                raw_sha256="b" * 64,
                raw_storage_key="emails/key",
                attachment_count=0,
                created_at=datetime.now(UTC),
            ),
            created=True,
            duplicate_reason=None,
        )


def _job(payload: dict[str, object]) -> JobRecord:
    now = datetime.now(UTC)
    return JobRecord(
        id=uuid4(),
        job_type=EMAIL_INGESTION_JOB,
        idempotency_key="email-ingest-test",
        payload=payload,
        status=JobStatus.RUNNING,
        priority=0,
        attempts=1,
        max_attempts=3,
        available_at=now,
        locked_by="test",
        started_at=now,
        heartbeat_at=now,
        finished_at=None,
        last_error=None,
        created_at=now,
        updated_at=now,
    )


def test_handler_dispatches_stable_uid_identity() -> None:
    account_id = uuid4()
    service = FakeIngestor()
    EmailIngestionJobHandler(service)(
        _job(
            {
                "mail_account_id": str(account_id),
                "folder": "INBOX",
                "uidvalidity": 17,
                "uid": 99,
            }
        )
    )
    assert service.calls == [(account_id, EmailMessageLocator("INBOX", 17, 99))]


def test_handler_rejects_missing_or_nonpositive_identity() -> None:
    with pytest.raises(ValueError, match="uid"):
        EmailIngestionJobHandler(FakeIngestor())(
            _job(
                {
                    "mail_account_id": str(uuid4()),
                    "folder": "INBOX",
                    "uidvalidity": 1,
                    "uid": 0,
                }
            )
        )
