"""Infrastructure-independent durable-job records."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class JobStatus(StrEnum):
    """Persisted lifecycle states for a durable job."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class JobRecord:
    """Stable job data passed to handlers and API serializers."""

    id: UUID
    job_type: str
    idempotency_key: str
    payload: dict[str, Any]
    status: JobStatus
    priority: int
    attempts: int
    max_attempts: int
    available_at: datetime
    locked_by: str | None
    started_at: datetime | None
    heartbeat_at: datetime | None
    finished_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
