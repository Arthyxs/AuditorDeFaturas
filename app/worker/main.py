"""Durable PostgreSQL worker CLI and continuous process loop."""

import argparse
import os
import socket
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Thread

from app.application.services.ai import AIExecutionService, AIProviderRouter
from app.application.services.email_classification import (
    ClassificationFolders,
    EmailClassificationService,
)
from app.application.services.email_ingestion import EmailIngestionService
from app.application.services.invoice_intake import IMAPInvoiceIntakeAdapter, InvoiceIntakeService
from app.application.services.jobs import WORKER_TICK_JOB, PollScheduler
from app.application.services.tariff_selection import TariffSelectionService
from app.config import Settings, get_settings
from app.domain.jobs import JobRecord
from app.infrastructure.ai.openai_provider import OpenAIProvider
from app.infrastructure.ai.prompts import PromptRepository
from app.infrastructure.email.imap_provider import IMAPEmailProvider
from app.infrastructure.persistence.repositories import (
    PostgreSQLAITelemetryRepository,
    PostgreSQLEmailClassificationRepository,
    PostgreSQLJobQueue,
    PostgreSQLMailIngestionRepository,
    PostgreSQLTariffSelectionRepository,
)
from app.infrastructure.persistence.repositories.invoice_intake import (
    PostgreSQLIMAPInvoiceSourceRepository,
    PostgreSQLInvoiceIntakeRepository,
)
from app.infrastructure.persistence.session import create_database_engine, create_session_factory
from app.infrastructure.storage import LocalStorageProvider
from app.ports.jobs import JobQueue
from app.worker.heartbeat import write_heartbeat
from app.worker.jobs.email_classification import (
    EMAIL_CLASSIFICATION_JOB,
    EmailClassificationJobHandler,
)
from app.worker.jobs.email_ingestion import EMAIL_INGESTION_JOB, EmailIngestionJobHandler
from app.worker.jobs.invoice_intake import TARIFF_SELECTION_JOB
from app.worker.jobs.tariff_selection import TariffSelectionJobHandler

JobHandler = Callable[[JobRecord], None]


def _handle_worker_tick(_: JobRecord) -> None:
    """Acknowledge the durable scheduling/control tick introduced by M09."""


class WorkerRunner:
    """Claim and execute at most one durable job per iteration."""

    def __init__(
        self,
        queue: JobQueue,
        settings: Settings,
        *,
        worker_id: str,
        handlers: dict[str, JobHandler] | None = None,
    ) -> None:
        self._queue = queue
        self._settings = settings
        self._worker_id = worker_id
        self._handlers = {WORKER_TICK_JOB: _handle_worker_tick}
        if handlers:
            self._handlers.update(handlers)
        self._scheduler = PollScheduler(
            queue,
            interval_minutes=settings.email_check_interval_minutes,
            max_attempts=settings.worker_max_attempts,
        )

    def run_once(self, *, include_schedule: bool = True) -> JobRecord | None:
        """Recover abandoned work, optionally schedule a tick, and execute one job."""
        now = datetime.now(UTC)
        self._queue.recover_stale(
            now=now,
            lease_timeout=timedelta(seconds=self._settings.worker_job_lease_seconds),
            retry_delay=timedelta(seconds=self._settings.worker_retry_base_seconds),
        )
        if include_schedule:
            self._scheduler.enqueue_due(now)
        job = self._queue.claim(
            worker_id=self._worker_id,
            now=now,
            job_types=tuple(self._handlers),
        )
        if job is None:
            return None

        with self._queue.execution_guard(job.id):
            stop_heartbeat = Event()
            heartbeat_thread = Thread(
                target=self._renew_lease,
                args=(job, stop_heartbeat),
                name=f"job-heartbeat-{job.id}",
                daemon=True,
            )
            heartbeat_thread.start()
            try:
                handler = self._handlers.get(job.job_type)
                if handler is None:
                    raise LookupError(f"no handler registered for job type {job.job_type!r}")
                handler(job)
            except Exception as exc:
                self._queue.fail(
                    job.id,
                    worker_id=self._worker_id,
                    now=datetime.now(UTC),
                    error=_safe_error(exc),
                    retry_delay=self._retry_delay(job.attempts),
                )
            else:
                self._queue.succeed(job.id, worker_id=self._worker_id, now=datetime.now(UTC))
            finally:
                stop_heartbeat.set()
                heartbeat_thread.join(timeout=self._settings.worker_heartbeat_interval_seconds + 1)
        return job

    def _retry_delay(self, attempts: int) -> timedelta:
        seconds = self._settings.worker_retry_base_seconds * (2 ** max(0, attempts - 1))
        return timedelta(seconds=min(seconds, self._settings.worker_retry_max_seconds))

    def _renew_lease(self, job: JobRecord, stop: Event) -> None:
        interval = self._settings.worker_heartbeat_interval_seconds
        while not stop.wait(interval):
            write_heartbeat()
            if not self._queue.heartbeat(job.id, worker_id=self._worker_id, now=datetime.now(UTC)):
                return


def _safe_error(exc: Exception) -> str:
    """Persist an explicit class/message without credential-shaped details."""
    message = str(exc).replace("\r", " ").replace("\n", " ")[:1000]
    lowered = message.casefold()
    sensitive_markers = ("password", "secret", "token", "api_key", "apikey", "://")
    if any(marker in lowered for marker in sensitive_markers):
        message = "sensitive exception detail redacted"
    return f"{type(exc).__name__}: {message or 'background job failed'}"


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def run(settings: Settings | None = None, *, once: bool = False) -> None:
    """Run one iteration or poll continuously according to typed configuration."""
    resolved_settings = get_settings() if settings is None else settings
    if not resolved_settings.worker_enabled:
        return
    engine = create_database_engine(resolved_settings)
    session_factory = create_session_factory(engine)
    queue = PostgreSQLJobQueue(session_factory)
    email_provider = None
    handlers: dict[str, JobHandler] = {}
    openai_key = (
        resolved_settings.openai_api_key.get_secret_value()
        if resolved_settings.openai_api_key
        else None
    )
    ai = AIExecutionService(
        router=AIProviderRouter(
            {
                "openai": OpenAIProvider(
                    api_key=openai_key,
                    timeout_seconds=resolved_settings.ai_timeout_seconds,
                )
            }
        ),
        telemetry=PostgreSQLAITelemetryRepository(session_factory),
    )
    prompts = PromptRepository(
        Path(__file__).resolve().parents[1] / "infrastructure" / "ai" / "prompts"
    )
    password = (
        resolved_settings.imap_password.get_secret_value()
        if resolved_settings.imap_password
        else ""
    )
    if resolved_settings.imap_host and resolved_settings.imap_user and password:
        email_provider = IMAPEmailProvider(
            host=resolved_settings.imap_host,
            port=resolved_settings.imap_port,
            username=resolved_settings.imap_user,
            password=password,
            implicit_tls=resolved_settings.imap_ssl,
            starttls=resolved_settings.imap_starttls,
            timeout_seconds=resolved_settings.imap_timeout_seconds,
            thread_scan_limit=resolved_settings.imap_thread_scan_limit,
        )
        storage = LocalStorageProvider(
            resolved_settings.storage_root,
            max_upload_size_bytes=resolved_settings.upload_max_size_bytes,
        )
        handlers[EMAIL_INGESTION_JOB] = EmailIngestionJobHandler(
            EmailIngestionService(
                email_provider=email_provider,
                storage=storage,
                repository=PostgreSQLMailIngestionRepository(session_factory),
            ),
            classification_queue=queue,
            max_attempts=resolved_settings.worker_max_attempts,
        )
        handlers[EMAIL_CLASSIFICATION_JOB] = EmailClassificationJobHandler(
            EmailClassificationService(
                repository=PostgreSQLEmailClassificationRepository(session_factory),
                email_provider=email_provider,
                ai=ai,
                prompt_provider=prompts,
                provider=resolved_settings.ai_email_provider,
                model=resolved_settings.ai_email_model,
                min_confidence=resolved_settings.email_classification_min_confidence,
                folders=ClassificationFolders(
                    resolved_settings.imap_folder_invoices,
                    resolved_settings.imap_folder_due_notices,
                    resolved_settings.imap_folder_general,
                    resolved_settings.imap_folder_review,
                ),
                thread_max_messages=resolved_settings.email_thread_max_messages,
                thread_max_characters=resolved_settings.email_thread_max_characters,
            ),
            invoice_intake=IMAPInvoiceIntakeAdapter(
                source_repository=PostgreSQLIMAPInvoiceSourceRepository(session_factory),
                intake=InvoiceIntakeService(
                    repository=PostgreSQLInvoiceIntakeRepository(session_factory),
                    queue=queue,
                    max_attempts=resolved_settings.worker_max_attempts,
                ),
            ),
        )
    handlers[TARIFF_SELECTION_JOB] = TariffSelectionJobHandler(
        TariffSelectionService(
            repository=PostgreSQLTariffSelectionRepository(session_factory),
            ai=ai,
            prompt_provider=prompts,
            provider=resolved_settings.ai_tariff_selector_provider,
            model=resolved_settings.ai_tariff_selector_model,
            min_confidence=resolved_settings.tariff_selection_min_confidence,
        )
    )
    runner = WorkerRunner(queue, resolved_settings, worker_id=_worker_id(), handlers=handlers)
    try:
        write_heartbeat()
        if once:
            runner.run_once()
            return
        while True:
            write_heartbeat()
            runner.run_once()
            time.sleep(resolved_settings.worker_poll_interval_seconds)
    finally:
        if email_provider is not None:
            email_provider.close()
        engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the supported worker mode and return a process exit code."""
    parser = argparse.ArgumentParser(description="InvoiceAuditor durable worker")
    parser.add_argument("--once", action="store_true", help="process at most one job and exit")
    arguments = parser.parse_args(argv)
    run(once=arguments.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
