"""Worker-control HTTP schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.jobs import JobStatus


class ProcessNowRequest(BaseModel):
    """Optional client key makes retried manual requests idempotent."""

    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class ProcessNowResponse(BaseModel):
    """Durable job accepted by the PostgreSQL queue."""

    job_id: UUID
    status: JobStatus
    idempotency_key: str
    available_at: datetime
    created: bool
