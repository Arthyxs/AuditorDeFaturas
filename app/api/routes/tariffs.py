"""Authenticated tariff catalog API."""

from collections.abc import Iterator
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_database, get_storage, require_roles, verify_same_origin
from app.api.schemas.tariffs import (
    TariffListResponse,
    TariffResponse,
    TariffUpdateRequest,
    TariffUploadResponse,
)
from app.application.services.tariffs import (
    TariffNotFoundError,
    TariffService,
    TariffVersionConflictError,
)
from app.domain.tariffs.models import TariffRecord
from app.infrastructure.persistence.models import User, UserRole
from app.infrastructure.persistence.repositories.tariffs import TariffRepository
from app.infrastructure.storage.validation import UploadValidationError
from app.ports.storage import StorageProvider

router = APIRouter(prefix="/api/tariffs", tags=["tariffs"])
Reader = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER))]
Writer = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))]
Database = Annotated[Session, Depends(get_database)]
Storage = Annotated[StorageProvider, Depends(get_storage)]


def _service(database: Session, storage: StorageProvider) -> TariffService:
    return TariffService(TariffRepository(database), storage)


def _response(tariff: TariffRecord) -> TariffResponse:
    return TariffResponse.model_validate(tariff)


def _not_found(exc: TariffNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tariff not found")


@router.get("", response_model=TariffListResponse)
def list_tariffs(
    _: Reader,
    database: Database,
    storage: Storage,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    active: bool | None = None,
    include_deleted: bool = False,
    search: Annotated[str | None, Query(max_length=255)] = None,
) -> TariffListResponse:
    """List tariff metadata using stable, mandatory pagination."""
    del storage
    items, total = TariffRepository(database).list_page(
        page=page,
        page_size=page_size,
        active=active,
        include_deleted=include_deleted,
        search=search,
    )
    pages = (total + page_size - 1) // page_size
    return TariffListResponse(
        items=[_response(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
        pages=pages,
    )


@router.post(
    "",
    response_model=TariffUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_same_origin)],
)
def upload_tariffs(
    user: Writer,
    database: Database,
    storage: Storage,
    files: Annotated[list[UploadFile], File()],
    description: Annotated[str | None, Form(max_length=4000)] = None,
    notes: Annotated[str | None, Form(max_length=4000)] = None,
) -> TariffUploadResponse:
    """Validate and publish one or more independent tariff originals."""
    if not files:
        raise HTTPException(status_code=422, detail="at least one file is required")
    service = _service(database, storage)
    created: list[TariffRecord] = []
    try:
        for upload in files:
            created.append(
                service.upload(
                    filename=upload.filename or "",
                    mime_type=upload.content_type or "application/octet-stream",
                    source=upload.file,
                    uploaded_by_id=user.id,
                    description=description,
                    notes=notes,
                )
            )
    except UploadValidationError as exc:
        database.rollback()
        for tariff in created:
            service.compensate_uncommitted_upload(tariff.storage_key)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TariffUploadResponse(items=[_response(item) for item in created])


@router.post(
    "/{tariff_id}/versions",
    response_model=TariffResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_same_origin)],
)
def upload_tariff_version(
    tariff_id: UUID,
    user: Writer,
    database: Database,
    storage: Storage,
    file: Annotated[UploadFile, File()],
    description: Annotated[str | None, Form(max_length=4000)] = None,
    notes: Annotated[str | None, Form(max_length=4000)] = None,
) -> TariffResponse:
    """Append a new immutable version to the current lineage tip."""
    try:
        tariff = _service(database, storage).upload_version(
            tariff_id,
            filename=file.filename or "",
            mime_type=file.content_type or "application/octet-stream",
            source=file.file,
            uploaded_by_id=user.id,
            description=description,
            notes=notes,
        )
    except TariffNotFoundError as exc:
        raise _not_found(exc) from exc
    except TariffVersionConflictError as exc:
        raise HTTPException(
            status_code=409, detail="a newer tariff version already exists"
        ) from exc
    except UploadValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _response(tariff)


@router.get("/{tariff_id}", response_model=TariffResponse)
def get_tariff(tariff_id: UUID, _: Reader, database: Database, storage: Storage) -> TariffResponse:
    """Return one tariff version, including soft-deleted metadata."""
    try:
        return _response(_service(database, storage).get(tariff_id))
    except TariffNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/{tariff_id}/versions", response_model=list[TariffResponse])
def list_tariff_versions(
    tariff_id: UUID, _: Reader, database: Database, storage: Storage
) -> list[TariffResponse]:
    """Return the complete append-only version lineage."""
    try:
        tariff = _service(database, storage).get(tariff_id)
    except TariffNotFoundError as exc:
        raise _not_found(exc) from exc
    return [
        _response(item) for item in TariffRepository(database).versions(tariff.version_group_id)
    ]


@router.patch(
    "/{tariff_id}",
    response_model=TariffResponse,
    dependencies=[Depends(verify_same_origin)],
)
def update_tariff(
    tariff_id: UUID,
    payload: TariffUpdateRequest,
    _: Writer,
    database: Database,
    storage: Storage,
) -> TariffResponse:
    """Edit catalog metadata without replacing or rewriting the original blob."""
    try:
        tariff = _service(database, storage).update(
            tariff_id,
            description=payload.description,
            notes=payload.notes,
            active=payload.active,
            supplied_fields=payload.model_fields_set,
        )
    except TariffNotFoundError as exc:
        raise _not_found(exc) from exc
    return _response(tariff)


@router.delete(
    "/{tariff_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_same_origin)],
)
def delete_tariff(tariff_id: UUID, _: Writer, database: Database, storage: Storage) -> Response:
    """Soft-delete catalog visibility while preserving all referenced bytes."""
    try:
        _service(database, storage).soft_delete(tariff_id)
    except TariffNotFoundError as exc:
        raise _not_found(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _stream_file(storage: StorageProvider, key: str) -> Iterator[bytes]:
    with storage.open_read(key) as stream:
        while chunk := stream.read(1024 * 1024):
            yield chunk


@router.get("/{tariff_id}/download")
def download_tariff(
    tariff_id: UUID, _: Reader, database: Database, storage: Storage
) -> StreamingResponse:
    """Stream integrity-verified bytes without exposing a filesystem path."""
    try:
        tariff = _service(database, storage).get(tariff_id)
    except TariffNotFoundError as exc:
        raise _not_found(exc) from exc
    encoded = quote(tariff.original_filename)
    return StreamingResponse(
        _stream_file(storage, tariff.storage_key),
        media_type=tariff.mime_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )
