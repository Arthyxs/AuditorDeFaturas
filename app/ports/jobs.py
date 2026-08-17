"""Port for durable PostgreSQL-independent job orchestration."""

from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from app.domain.jobs import JobRecord


class JobQueue(Protocol):
    """Operations required by the API, scheduler and worker runner."""

    def enqueue(
        self,
        *,
        job_type: str,
        idempotency_key: str,
        payload: dict[str, Any],
        max_attempts: int,
        available_at: datetime,
        priority: int = 0,
    ) -> tuple[JobRecord, bool]: ...

    def claim(
        self,
        *,
        worker_id: str,
        now: datetime,
        job_types: tuple[str, ...] | None = None,
    ) -> JobRecord | None: ...

    def execution_guard(self, job_id: UUID) -> AbstractContextManager[None]:
        """Hold a crash-released guard preventing stale recovery during active execution."""

    def heartbeat(self, job_id: UUID, *, worker_id: str, now: datetime) -> bool: ...

    def succeed(self, job_id: UUID, *, worker_id: str, now: datetime) -> JobRecord: ...

    def fail(
        self,
        job_id: UUID,
        *,
        worker_id: str,
        now: datetime,
        error: str,
        retry_delay: timedelta,
    ) -> JobRecord: ...

    def recover_stale(
        self, *, now: datetime, lease_timeout: timedelta, retry_delay: timedelta
    ) -> list[JobRecord]: ...
