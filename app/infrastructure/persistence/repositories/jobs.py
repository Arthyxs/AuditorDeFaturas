"""PostgreSQL durable queue adapter."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.jobs import JobRecord, JobStatus
from app.infrastructure.persistence.models import ProcessingJob
from app.infrastructure.persistence.session import SessionFactory, session_scope


class JobLeaseError(RuntimeError):
    """Raised when a worker attempts to finish a lease it no longer owns."""


def _record(job: ProcessingJob) -> JobRecord:
    return JobRecord(
        id=job.id,
        job_type=job.job_type,
        idempotency_key=job.idempotency_key,
        payload=job.payload,
        status=job.status,
        priority=job.priority,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        available_at=job.available_at,
        locked_by=job.locked_by,
        started_at=job.started_at,
        heartbeat_at=job.heartbeat_at,
        finished_at=job.finished_at,
        last_error=job.last_error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


class PostgreSQLJobQueue:
    """Transactionally claim, lease and finish jobs without an external broker."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        engine = session_factory.kw.get("bind")
        if not isinstance(engine, Engine):
            raise TypeError("job queue requires a SQLAlchemy Engine-bound session factory")
        self._engine = engine

    @contextmanager
    def execution_guard(self, job_id: UUID) -> Iterator[None]:
        """Hold a session advisory lock until the handler finishes or the process disconnects."""
        key = _execution_advisory_key(job_id)
        with self._engine.connect() as connection:
            connection.execute(select(func.pg_advisory_lock(key)))
            connection.commit()
            try:
                yield
            finally:
                connection.execute(select(func.pg_advisory_unlock(key)))
                connection.commit()

    def enqueue(
        self,
        *,
        job_type: str,
        idempotency_key: str,
        payload: dict[str, Any],
        max_attempts: int,
        available_at: datetime,
        priority: int = 0,
    ) -> tuple[JobRecord, bool]:
        job_id = uuid4()
        statement = (
            insert(ProcessingJob)
            .values(
                id=job_id,
                job_type=job_type,
                idempotency_key=idempotency_key,
                payload=payload,
                status=JobStatus.PENDING,
                priority=priority,
                attempts=0,
                max_attempts=max_attempts,
                available_at=available_at,
            )
            .on_conflict_do_nothing(index_elements=[ProcessingJob.idempotency_key])
            .returning(ProcessingJob.id)
        )
        with session_scope(self._session_factory) as database:
            inserted_id = database.scalar(statement)
            job = database.scalar(
                select(ProcessingJob).where(
                    ProcessingJob.id == (inserted_id if inserted_id is not None else job_id),
                )
            )
            if job is None and inserted_id is None:
                job = database.scalar(
                    select(ProcessingJob).where(ProcessingJob.idempotency_key == idempotency_key)
                )
            if job is None:
                raise RuntimeError("job enqueue did not return a durable record")
            return _record(job), inserted_id is not None

    def claim(
        self,
        *,
        worker_id: str,
        now: datetime,
        job_types: tuple[str, ...] | None = None,
    ) -> JobRecord | None:
        with session_scope(self._session_factory) as database:
            statement = select(ProcessingJob).where(
                ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RETRY_SCHEDULED]),
                ProcessingJob.available_at <= now,
            )
            if job_types is not None:
                if not job_types:
                    return None
                statement = statement.where(ProcessingJob.job_type.in_(job_types))
            job = database.scalar(
                statement.order_by(
                    ProcessingJob.priority.desc(),
                    ProcessingJob.available_at,
                    ProcessingJob.created_at,
                )
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return None
            job.status = JobStatus.RUNNING
            job.attempts += 1
            job.locked_by = worker_id
            job.started_at = now
            job.heartbeat_at = now
            job.finished_at = None
            database.flush()
            return _record(job)

    def heartbeat(self, job_id: UUID, *, worker_id: str, now: datetime) -> bool:
        with session_scope(self._session_factory) as database:
            job = database.scalar(
                select(ProcessingJob).where(ProcessingJob.id == job_id).with_for_update()
            )
            if job is None or job.status != JobStatus.RUNNING or job.locked_by != worker_id:
                return False
            job.heartbeat_at = now
            return True

    def succeed(self, job_id: UUID, *, worker_id: str, now: datetime) -> JobRecord:
        with session_scope(self._session_factory) as database:
            job = self._owned_running_job(database, job_id, worker_id)
            job.status = JobStatus.SUCCEEDED
            job.finished_at = now
            job.heartbeat_at = now
            job.locked_by = None
            job.last_error = None
            database.flush()
            return _record(job)

    def fail(
        self,
        job_id: UUID,
        *,
        worker_id: str,
        now: datetime,
        error: str,
        retry_delay: timedelta,
    ) -> JobRecord:
        with session_scope(self._session_factory) as database:
            job = self._owned_running_job(database, job_id, worker_id)
            job.last_error = error[:4000]
            job.heartbeat_at = now
            job.locked_by = None
            if job.attempts < job.max_attempts:
                job.status = JobStatus.RETRY_SCHEDULED
                job.available_at = now + retry_delay
                job.finished_at = None
            else:
                job.status = JobStatus.FAILED
                job.finished_at = now
            database.flush()
            return _record(job)

    def recover_stale(
        self, *, now: datetime, lease_timeout: timedelta, retry_delay: timedelta
    ) -> list[JobRecord]:
        cutoff = now - lease_timeout
        recovered: list[JobRecord] = []
        with session_scope(self._session_factory) as database:
            jobs = database.scalars(
                select(ProcessingJob)
                .where(
                    ProcessingJob.status == JobStatus.RUNNING,
                    or_(
                        ProcessingJob.heartbeat_at.is_(None),
                        ProcessingJob.heartbeat_at < cutoff,
                    ),
                )
                .with_for_update(skip_locked=True)
            ).all()
            for job in jobs:
                execution_finished = database.scalar(
                    select(func.pg_try_advisory_xact_lock(_execution_advisory_key(job.id)))
                )
                if not execution_finished:
                    continue
                job.last_error = "worker lease expired before completion"
                job.locked_by = None
                if job.attempts < job.max_attempts:
                    job.status = JobStatus.RETRY_SCHEDULED
                    job.available_at = now + retry_delay
                    job.finished_at = None
                else:
                    job.status = JobStatus.FAILED
                    job.finished_at = now
                recovered.append(_record(job))
        return recovered

    @staticmethod
    def _owned_running_job(database: Session, job_id: UUID, worker_id: str) -> ProcessingJob:
        job = database.scalar(
            select(ProcessingJob).where(ProcessingJob.id == job_id).with_for_update()
        )
        if job is None or job.status != JobStatus.RUNNING or job.locked_by != worker_id:
            raise JobLeaseError("worker no longer owns this running job")
        return job


def _execution_advisory_key(job_id: UUID) -> int:
    payload = sha256(f"job-execution:{job_id}".encode("ascii")).digest()[:8]
    unsigned = int.from_bytes(payload, "big")
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned
