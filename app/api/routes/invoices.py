"""Authenticated manual entry into the canonical invoice intake."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from pydantic import ValidationError

from app.api.dependencies import get_storage, require_roles, verify_same_origin
from app.api.schemas.invoices import InvoiceResponse, ManualInvoiceResponse
from app.application.services.invoice_intake import InvoiceIntakeService, canonical_submission_hash
from app.domain.intake.models import (
    InvoiceMetadata,
    InvoiceSubmissionCommand,
    SubmissionFileInput,
    SubmissionFileRole,
    SubmissionSource,
)
from app.infrastructure.persistence.models import User, UserRole
from app.infrastructure.persistence.repositories.invoice_intake import (
    PostgreSQLInvoiceIntakeRepository,
)
from app.infrastructure.persistence.repositories.jobs import PostgreSQLJobQueue
from app.infrastructure.storage.validation import UploadValidationError
from app.ports.storage import PhysicalDeletionApproval, StorageProvider, StoredFileMetadata

router = APIRouter(prefix="/api/invoices", tags=["invoices"])
Writer = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))]
Storage = Annotated[StorageProvider, Depends(get_storage)]


def _delete_unreferenced(storage: StorageProvider, files: list[StoredFileMetadata]) -> None:
    approval = PhysicalDeletionApproval(
        reason="compensate unreferenced duplicate manual invoice upload",
        references_checked=True,
    )
    for item in reversed(files):
        storage.delete(item.key, approval=approval)


@router.post(
    "/manual",
    response_model=ManualInvoiceResponse,
    status_code=201,
    dependencies=[Depends(verify_same_origin)],
)
def submit_manual_invoice(
    request: Request,
    user: Writer,
    storage: Storage,
    invoice: Annotated[UploadFile, File()],
    attachments: Annotated[list[UploadFile] | None, File()] = None,
    metadata: Annotated[str | None, Form()] = None,
    note: Annotated[str | None, Form(max_length=4000)] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=200)] = None,
) -> ManualInvoiceResponse:
    try:
        parsed_metadata = InvoiceMetadata.model_validate_json(metadata or "{}")
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="invalid canonical invoice metadata") from exc

    uploads = [(SubmissionFileRole.INVOICE, invoice)] + [
        (SubmissionFileRole.AUXILIARY, item) for item in (attachments or [])
    ]
    stored: list[StoredFileMetadata] = []
    try:
        for _, upload in uploads:
            stored.append(
                storage.store(
                    "invoices",
                    upload.filename or "",
                    upload.content_type or "application/octet-stream",
                    upload.file,
                )
            )
    except UploadValidationError as exc:
        _delete_unreferenced(storage, stored)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    files = tuple(
        SubmissionFileInput(
            role=role,
            ordinal=ordinal,
            original_filename=item.original_filename,
            mime_type=item.mime_type,
            size=item.size,
            sha256=item.sha256,
            storage_key=item.key,
        )
        for ordinal, ((role, _), item) in enumerate(zip(uploads, stored, strict=True))
    )
    content_hash = canonical_submission_hash(
        source=SubmissionSource.MANUAL,
        files=files,
        metadata=parsed_metadata,
    )
    command = InvoiceSubmissionCommand(
        source=SubmissionSource.MANUAL,
        idempotency_key=f"manual:{idempotency_key or content_hash}",
        content_hash=content_hash,
        mail_message_id=None,
        submitted_by_id=user.id,
        files=files,
        metadata=parsed_metadata,
        note=note,
    )
    service = InvoiceIntakeService(
        repository=PostgreSQLInvoiceIntakeRepository(request.app.state.session_factory),
        queue=PostgreSQLJobQueue(request.app.state.session_factory),
        max_attempts=request.app.state.settings.worker_max_attempts,
    )
    try:
        result = service.submit(command)
    except ValueError as exc:
        _delete_unreferenced(storage, stored)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result.created:
        _delete_unreferenced(storage, stored)
    return ManualInvoiceResponse(
        invoice=InvoiceResponse.model_validate(result.invoice),
        created=result.created,
    )
