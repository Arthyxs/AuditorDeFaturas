"""Durable PostgreSQL worker CLI and continuous process loop."""

import argparse
import os
import socket
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from threading import Event, Thread

from app.application.services.jobs import WORKER_TICK_JOB, PollScheduler
from app.config import Settings, get_settings
from app.domain.jobs import JobRecord
from app.infrastructure.persistence.repositories import PostgreSQLJobQueue
from app.infrastructure.persistence.session import create_database_engine, create_session_factory
from app.ports.jobs import JobQueue
from app.worker.heartbeat import write_heartbeat

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
        job = self._queue.claim(worker_id=self._worker_id, now=now)
        if job is None:
            return None

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
    queue = PostgreSQLJobQueue(create_session_factory(engine))
    runner = WorkerRunner(queue, resolved_settings, worker_id=_worker_id())
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
