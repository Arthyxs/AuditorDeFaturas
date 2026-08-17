"""Minimal authenticated review API for low-confidence e-mail classification."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.dependencies import require_roles, verify_same_origin
from app.api.schemas.emails import EmailReviewListResponse, EmailReviewRequest, EmailReviewResponse
from app.config import Settings
from app.domain.email.classification import EmailClassificationRecord
from app.infrastructure.persistence.models import User, UserRole
from app.infrastructure.persistence.repositories import (
    PostgreSQLEmailClassificationRepository,
    PostgreSQLJobQueue,
)
from app.worker.jobs.email_classification import EMAIL_CLASSIFICATION_JOB

router = APIRouter(prefix="/api/emails", tags=["emails"])
Reader = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER))]
Reviewer = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))]


def _response(record: EmailClassificationRecord) -> EmailReviewResponse:
    return EmailReviewResponse.model_validate(record)


@router.get("/review", response_model=EmailReviewListResponse)
def list_review(
    request: Request,
    _: Reader,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> EmailReviewListResponse:
    repository = PostgreSQLEmailClassificationRepository(request.app.state.session_factory)
    records, total = repository.list_manual_review(page=page, page_size=page_size)
    return EmailReviewListResponse(
        items=[_response(record) for record in records],
        page=page,
        page_size=page_size,
        total=total,
        pages=(total + page_size - 1) // page_size,
    )


@router.patch(
    "/{message_id}/review",
    response_model=EmailReviewResponse,
    dependencies=[Depends(verify_same_origin)],
)
def resolve_review(
    message_id: UUID,
    payload: EmailReviewRequest,
    user: Reviewer,
    request: Request,
) -> EmailReviewResponse:
    repository = PostgreSQLEmailClassificationRepository(request.app.state.session_factory)
    try:
        record = repository.resolve_manual_review(
            message_id,
            classification=payload.classification,
            reviewer_id=user.id,
            note=payload.note,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="e-mail not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    settings: Settings = request.app.state.settings
    PostgreSQLJobQueue(request.app.state.session_factory).enqueue(
        job_type=EMAIL_CLASSIFICATION_JOB,
        idempotency_key=f"email.review.move:{message_id}:{record.classification.value}",
        payload={"mail_message_id": str(message_id)},
        max_attempts=settings.worker_max_attempts,
        available_at=datetime.now(UTC),
        priority=10,
    )
    return _response(record)
