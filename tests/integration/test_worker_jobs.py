"""M09 durable worker, scheduler, endpoint and lock acceptance tests."""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Thread
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine, make_url

from app.application.services.jobs import PollScheduler
from app.config import Settings, get_settings
from app.domain.jobs import JobStatus
from app.infrastructure.persistence.invoice_locks import try_invoice_lock
from app.infrastructure.persistence.models import ProcessingJob, User, UserRole
from app.infrastructure.persistence.repositories import PostgreSQLJobQueue
from app.infrastructure.persistence.session import create_session_factory
from app.infrastructure.security.passwords import hash_password
from app.main import create_app
from app.worker.main import WorkerRunner
from app.worker.main import main as worker_main

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 with a disposable PostgreSQL server",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "https://invoice-auditor.test"
PASSWORD = "test-only-password-123"


@pytest.fixture
def postgres_database_url() -> Iterator[str]:
    """Create an isolated M09 database migrated to current head."""
    configured_url = make_url(get_settings().database_url.get_secret_value())
    database_name = f"invoice_auditor_m09_{uuid4().hex}"
    admin_url = configured_url.set(database="postgres")
    test_url = configured_url.set(database=database_name)
    admin_engine = create_engine(
        admin_url.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    database_url = test_url.render_as_string(hide_password=False)
    configuration = Config(str(PROJECT_ROOT / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(configuration, "head")
    try:
        yield database_url
    finally:
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        admin_engine.dispose()


@pytest.fixture
def database_engine(postgres_database_url: str) -> Iterator[Engine]:
    engine = create_engine(postgres_database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def queue(database_engine: Engine) -> PostgreSQLJobQueue:
    return PostgreSQLJobQueue(create_session_factory(database_engine))


def _settings(database_url: str, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "test",
        "app_base_url": ORIGIN,
        "app_secret_key": "test-app-secret-000000000000000000000000000",
        "first_admin_bootstrap_token": "test-bootstrap-token-000000000000000000000000",
        "postgres_password": "test-postgres-secret-00000000000000000000000",
        "database_url": database_url,
        "worker_heartbeat_interval_seconds": 30,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def _enqueue(
    queue: PostgreSQLJobQueue,
    key: str,
    *,
    job_type: str = "test.job",
    max_attempts: int = 3,
    available_at: datetime | None = None,
) -> ProcessingJob:
    record, _ = queue.enqueue(
        job_type=job_type,
        idempotency_key=key,
        payload={"fixture": True},
        max_attempts=max_attempts,
        available_at=available_at or datetime.now(UTC),
    )
    return ProcessingJob(id=record.id)


def _load(engine: Engine, job_id: Any) -> ProcessingJob:
    with create_session_factory(engine)() as database:
        job = database.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id))
        assert job is not None
        database.expunge(job)
        return job


def test_idempotent_enqueue_and_two_workers_claim_only_once(
    queue: PostgreSQLJobQueue,
) -> None:
    """A unique key maps to one row and SKIP LOCKED gives it to only one worker."""
    now = datetime.now(UTC)
    first, first_created = queue.enqueue(
        job_type="test.job",
        idempotency_key="same-business-command",
        payload={"version": 1},
        max_attempts=3,
        available_at=now,
    )
    duplicate, duplicate_created = queue.enqueue(
        job_type="test.job",
        idempotency_key="same-business-command",
        payload={"version": 2},
        max_attempts=3,
        available_at=now,
    )
    assert first_created is True
    assert duplicate_created is False
    assert duplicate.id == first.id
    assert duplicate.payload == {"version": 1}

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(
            executor.map(
                lambda worker: queue.claim(worker_id=worker, now=now),
                ["worker-a", "worker-b"],
            )
        )
    claimed = [job for job in claims if job is not None]
    assert len(claimed) == 1
    assert claimed[0].id == first.id
    assert claimed[0].attempts == 1


def test_retry_backoff_then_explicit_failure(
    queue: PostgreSQLJobQueue, database_engine: Engine, postgres_database_url: str
) -> None:
    """Handler failures retry with backoff and become FAILED at the attempt limit."""
    job = _enqueue(queue, "retry-job", job_type="always.fail", max_attempts=2)
    settings = _settings(
        postgres_database_url,
        worker_retry_base_seconds=3,
        worker_retry_max_seconds=10,
    )

    def fail(_: Any) -> None:
        raise RuntimeError("synthetic handler failure")

    runner = WorkerRunner(queue, settings, worker_id="retry-worker", handlers={"always.fail": fail})
    runner.run_once(include_schedule=False)
    after_first = _load(database_engine, job.id)
    assert after_first.status == JobStatus.RETRY_SCHEDULED
    assert after_first.attempts == 1
    assert after_first.last_error == "RuntimeError: synthetic handler failure"
    assert after_first.available_at >= after_first.heartbeat_at + timedelta(seconds=3)  # type: ignore[operator]

    with create_session_factory(database_engine)() as database:
        persisted = database.get(ProcessingJob, job.id)
        assert persisted is not None
        persisted.available_at = datetime.now(UTC) - timedelta(seconds=1)
        database.commit()
    runner.run_once(include_schedule=False)
    after_second = _load(database_engine, job.id)
    assert after_second.status == JobStatus.FAILED
    assert after_second.attempts == 2
    assert after_second.finished_at is not None


def test_heartbeat_and_crash_recovery_are_lease_safe(
    queue: PostgreSQLJobQueue, database_engine: Engine
) -> None:
    """A stale RUNNING job is made retryable, while a live lease can be renewed."""
    old = datetime.now(UTC) - timedelta(minutes=10)
    job = _enqueue(queue, "crashed-job", available_at=old)
    claimed = queue.claim(worker_id="crashed-worker", now=old)
    assert claimed is not None
    now = datetime.now(UTC)
    recovered = queue.recover_stale(
        now=now,
        lease_timeout=timedelta(seconds=60),
        retry_delay=timedelta(seconds=2),
    )
    assert [item.id for item in recovered] == [job.id]
    persisted = _load(database_engine, job.id)
    assert persisted.status == JobStatus.RETRY_SCHEDULED
    assert persisted.locked_by is None
    assert persisted.last_error == "worker lease expired before completion"

    with create_session_factory(database_engine)() as database:
        mutable_job = database.get(ProcessingJob, job.id)
        assert mutable_job is not None
        mutable_job.available_at = now
        database.commit()
    resumed = queue.claim(worker_id="replacement-worker", now=now)
    assert resumed is not None
    heartbeat_time = now + timedelta(seconds=1)
    assert queue.heartbeat(resumed.id, worker_id="replacement-worker", now=heartbeat_time)
    assert not queue.heartbeat(resumed.id, worker_id="wrong-worker", now=heartbeat_time)
    completed = queue.succeed(resumed.id, worker_id="replacement-worker", now=heartbeat_time)
    assert completed.status == JobStatus.SUCCEEDED


def test_stale_recovery_cannot_reclaim_an_active_handler(
    queue: PostgreSQLJobQueue, database_engine: Engine, postgres_database_url: str
) -> None:
    job = _enqueue(queue, "guarded-handler", job_type="guarded.handler")
    entered = Event()
    release = Event()

    def handler(_: Any) -> None:
        entered.set()
        assert release.wait(timeout=10)

    runner = WorkerRunner(
        queue,
        _settings(
            postgres_database_url,
            worker_heartbeat_interval_seconds=30,
            worker_job_lease_seconds=5,
        ),
        worker_id="guarded-worker",
        handlers={"guarded.handler": handler},
    )
    thread = Thread(target=lambda: runner.run_once(include_schedule=False))
    thread.start()
    assert entered.wait(timeout=10)

    recovered = queue.recover_stale(
        now=datetime.now(UTC) + timedelta(minutes=1),
        lease_timeout=timedelta(seconds=1),
        retry_delay=timedelta(seconds=1),
    )
    assert recovered == []
    assert _load(database_engine, job.id).status == JobStatus.RUNNING

    release.set()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert _load(database_engine, job.id).status == JobStatus.SUCCEEDED


def test_scheduling_uses_window_keys_and_respects_availability(
    queue: PostgreSQLJobQueue,
) -> None:
    """Polling windows are idempotent and future work cannot be claimed early."""
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
    scheduler = PollScheduler(queue, interval_minutes=15, max_attempts=4)
    first, created = scheduler.enqueue_due(now)
    duplicate, duplicate_created = scheduler.enqueue_due(now + timedelta(minutes=14))
    next_window, next_created = scheduler.enqueue_due(now + timedelta(minutes=15))
    assert created is True
    assert duplicate_created is False
    assert duplicate.id == first.id
    assert next_created is True
    assert next_window.id != first.id

    _enqueue(queue, "future-job", available_at=now + timedelta(days=1))
    first_claim = queue.claim(worker_id="scheduler-worker", now=now)
    second_claim = queue.claim(worker_id="scheduler-worker", now=now)
    assert first_claim is not None
    assert second_claim is None
    next_claim = queue.claim(worker_id="scheduler-worker", now=now + timedelta(minutes=15))
    assert next_claim is not None
    assert next_claim.id == next_window.id
    assert queue.claim(worker_id="scheduler-worker", now=now + timedelta(minutes=15)) is None


def test_invoice_advisory_lock_excludes_concurrent_transactions(database_engine: Engine) -> None:
    """Only one transaction can hold the stable lock for an invoice UUID."""
    session_factory = create_session_factory(database_engine)
    invoice_id = uuid4()
    first = session_factory()
    second = session_factory()
    try:
        assert try_invoice_lock(first, invoice_id)
        assert not try_invoice_lock(second, invoice_id)
        first.commit()
        second.rollback()
        assert try_invoice_lock(second, invoice_id)
    finally:
        first.rollback()
        second.rollback()
        first.close()
        second.close()


def test_once_processes_at_most_one_job_and_cli_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI forwards --once and never enters the continuous loop."""
    calls: list[bool] = []
    monkeypatch.setattr("app.worker.main.run", lambda *, once=False: calls.append(once))
    assert worker_main(["--once"]) == 0
    assert calls == [True]


def test_runner_once_leaves_second_ready_job_pending(
    queue: PostgreSQLJobQueue, database_engine: Engine, postgres_database_url: str
) -> None:
    """One runner iteration cannot drain more than one ready job."""
    first = _enqueue(queue, "once-first", job_type="once.success")
    second = _enqueue(queue, "once-second", job_type="once.success")
    handled: list[Any] = []
    runner = WorkerRunner(
        queue,
        _settings(postgres_database_url),
        worker_id="once-worker",
        handlers={"once.success": lambda job: handled.append(job.id)},
    )
    runner.run_once(include_schedule=False)
    statuses = {_load(database_engine, job.id).status for job in (first, second)}
    assert handled and len(handled) == 1
    assert statuses == {JobStatus.SUCCEEDED, JobStatus.PENDING}


def _app(database_url: str, tmp_path: Path) -> FastAPI:
    application = create_app(_settings(database_url, storage_root=tmp_path))
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


def test_process_now_endpoint_rbac_origin_and_idempotency(
    postgres_database_url: str, tmp_path: Path
) -> None:
    """Writers enqueue durable ticks; Viewer/origin violations cannot mutate the queue."""
    application = _app(postgres_database_url, tmp_path)
    with TestClient(application, base_url=ORIGIN) as client:
        _login(client, UserRole.OPERATOR)
        first = client.post(
            "/api/worker/run-now",
            headers={"Origin": ORIGIN},
            json={"idempotency_key": "operator-click-1"},
        )
        duplicate = client.post(
            "/api/worker/run-now",
            headers={"Origin": ORIGIN},
            json={"idempotency_key": "operator-click-1"},
        )
        assert first.status_code == 202
        assert first.json()["created"] is True
        assert duplicate.status_code == 202
        assert duplicate.json()["created"] is False
        assert duplicate.json()["job_id"] == first.json()["job_id"]
        assert client.post("/api/worker/run-now", json={}).status_code == 403

        client.post("/api/auth/logout", headers={"Origin": ORIGIN})
        _login(client, UserRole.VIEWER)
        forbidden = client.post("/api/worker/run-now", headers={"Origin": ORIGIN}, json={})
        assert forbidden.status_code == 403
    application.state.database_engine.dispose()
