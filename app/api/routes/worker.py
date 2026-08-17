"""Authenticated operational controls for the durable worker."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.dependencies import require_roles, verify_same_origin
from app.api.schemas.worker import ProcessNowRequest, ProcessNowResponse
from app.application.services.jobs import WorkerControlService
from app.config import Settings
from app.infrastructure.persistence.models import User, UserRole
from app.infrastructure.persistence.repositories import PostgreSQLJobQueue

router = APIRouter(prefix="/api/worker", tags=["worker"])
Writer = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))]


@router.post(
    "/run-now",
    response_model=ProcessNowResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_same_origin)],
)
def process_now(payload: ProcessNowRequest, user: Writer, request: Request) -> ProcessNowResponse:
    """Enqueue a manual tick and return the existing job on client retry."""
    settings: Settings = request.app.state.settings
    service = WorkerControlService(
        PostgreSQLJobQueue(request.app.state.session_factory),
        max_attempts=settings.worker_max_attempts,
    )
    job, created = service.process_now(
        requested_by_id=user.id,
        idempotency_key=payload.idempotency_key,
    )
    return ProcessNowResponse(
        job_id=job.id,
        status=job.status,
        idempotency_key=job.idempotency_key,
        available_at=job.available_at,
        created=created,
    )
