"""Application services for durable scheduling and manual worker triggers."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.domain.jobs import JobRecord
from app.ports.jobs import JobQueue

WORKER_TICK_JOB = "worker.tick"


class PollScheduler:
    """Materialize one durable tick per configured polling window."""

    def __init__(self, queue: JobQueue, *, interval_minutes: int, max_attempts: int) -> None:
        self._queue = queue
        self._interval_seconds = interval_minutes * 60
        self._max_attempts = max_attempts

    def enqueue_due(self, now: datetime | None = None) -> tuple[JobRecord, bool]:
        current = datetime.now(UTC) if now is None else now
        window = int(current.timestamp()) // self._interval_seconds
        return self._queue.enqueue(
            job_type=WORKER_TICK_JOB,
            idempotency_key=f"scheduled:worker-tick:{window}",
            payload={"trigger": "schedule", "window": window},
            max_attempts=self._max_attempts,
            available_at=current,
        )


class WorkerControlService:
    """Create auditable, idempotent manual processing ticks."""

    def __init__(self, queue: JobQueue, *, max_attempts: int) -> None:
        self._queue = queue
        self._max_attempts = max_attempts

    def process_now(
        self,
        *,
        requested_by_id: UUID,
        idempotency_key: str | None,
        now: datetime | None = None,
        extra_payload: dict[str, Any] | None = None,
    ) -> tuple[JobRecord, bool]:
        current = datetime.now(UTC) if now is None else now
        request_key = idempotency_key or str(uuid4())
        payload: dict[str, Any] = {
            "trigger": "manual",
            "requested_by_id": str(requested_by_id),
        }
        if extra_payload:
            payload.update(extra_payload)
        return self._queue.enqueue(
            job_type=WORKER_TICK_JOB,
            idempotency_key=f"manual:worker-tick:{request_key}",
            payload=payload,
            max_attempts=self._max_attempts,
            available_at=current,
            priority=10,
        )
