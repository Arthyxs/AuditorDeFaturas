"""PostgreSQL tariff catalog repository."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.domain.tariffs.models import TariffRecord
from app.infrastructure.persistence.models import TariffFile
from app.ports.storage import StoredFileMetadata


class TariffRepository:
    """Keep tariff models, queries and row locking inside the persistence adapter."""

    def __init__(self, database: Session) -> None:
        self._database = database

    def _add(self, tariff: TariffFile) -> TariffRecord:
        self._database.add(tariff)
        self._database.flush()
        return self._record(tariff)

    def create(
        self,
        stored: StoredFileMetadata,
        *,
        uploaded_by_id: UUID,
        description: str | None,
        notes: str | None,
    ) -> TariffRecord:
        return self._add(
            self._from_stored(
                stored,
                uploaded_by_id=uploaded_by_id,
                description=description,
                notes=notes,
            )
        )

    def create_version(
        self,
        previous: TariffRecord,
        stored: StoredFileMetadata,
        *,
        uploaded_by_id: UUID,
        description: str | None,
        notes: str | None,
    ) -> TariffRecord:
        previous_model = self._database.get(TariffFile, previous.id)
        if previous_model is None:
            raise RuntimeError("locked tariff disappeared")
        new_version = self._from_stored(
            stored,
            uploaded_by_id=uploaded_by_id,
            description=description,
            notes=notes,
        )
        new_version.version_group_id = previous.version_group_id
        new_version.previous_version_id = previous.id
        new_version.version = previous.version + 1
        previous_model.active = False
        return self._add(new_version)

    def get(self, tariff_id: UUID, *, lock: bool = False) -> TariffRecord | None:
        statement = select(TariffFile).where(TariffFile.id == tariff_id)
        if lock:
            statement = statement.with_for_update()
        model = self._database.scalar(statement)
        return None if model is None else self._record(model)

    def successor_exists(self, tariff_id: UUID) -> bool:
        return (
            self._database.scalar(
                select(TariffFile.id).where(TariffFile.previous_version_id == tariff_id).limit(1)
            )
            is not None
        )

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        active: bool | None,
        include_deleted: bool,
        search: str | None,
    ) -> tuple[list[TariffRecord], int]:
        filters: list[ColumnElement[bool]] = []
        if not include_deleted:
            filters.append(TariffFile.deleted_at.is_(None))
        if active is not None:
            filters.append(TariffFile.active.is_(active))
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    TariffFile.original_filename.ilike(pattern),
                    TariffFile.description.ilike(pattern),
                    TariffFile.notes.ilike(pattern),
                )
            )
        total = self._database.scalar(select(func.count()).select_from(TariffFile).where(*filters))
        items = self._database.scalars(
            select(TariffFile)
            .where(*filters)
            .order_by(TariffFile.created_at.desc(), TariffFile.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [self._record(item) for item in items], int(total or 0)

    def versions(self, group_id: UUID) -> list[TariffRecord]:
        return [
            self._record(item)
            for item in self._database.scalars(
                select(TariffFile)
                .where(TariffFile.version_group_id == group_id)
                .order_by(TariffFile.version)
            ).all()
        ]

    def update_metadata(
        self,
        tariff_id: UUID,
        *,
        description: str | None,
        notes: str | None,
        active: bool | None,
        supplied_fields: set[str],
    ) -> TariffRecord | None:
        tariff = self._database.get(TariffFile, tariff_id)
        if tariff is None or tariff.deleted_at is not None:
            return None
        if "description" in supplied_fields:
            tariff.description = description
        if "notes" in supplied_fields:
            tariff.notes = notes
        if "active" in supplied_fields and active is not None:
            tariff.active = active
        self._database.flush()
        return self._record(tariff)

    def soft_delete(self, tariff_id: UUID) -> bool:
        tariff = self._database.get(TariffFile, tariff_id)
        if tariff is None:
            return False
        if tariff.deleted_at is None:
            tariff.deleted_at = datetime.now(UTC)
            tariff.active = False
            self._database.flush()
        return True

    @staticmethod
    def _from_stored(
        stored: StoredFileMetadata,
        *,
        uploaded_by_id: UUID,
        description: str | None,
        notes: str | None,
    ) -> TariffFile:
        return TariffFile(
            original_filename=stored.original_filename,
            internal_filename=stored.internal_filename,
            extension=stored.extension,
            mime_type=stored.mime_type,
            size=stored.size,
            sha256=stored.sha256,
            storage_key=stored.key,
            description=description,
            notes=notes,
            active=True,
            uploaded_by_id=uploaded_by_id,
        )

    @staticmethod
    def _record(model: TariffFile) -> TariffRecord:
        return TariffRecord(
            id=model.id,
            original_filename=model.original_filename,
            internal_filename=model.internal_filename,
            extension=model.extension,
            mime_type=model.mime_type,
            size=model.size,
            sha256=model.sha256,
            storage_key=model.storage_key,
            description=model.description,
            notes=model.notes,
            active=model.active,
            version=model.version,
            version_group_id=model.version_group_id,
            previous_version_id=model.previous_version_id,
            uploaded_by_id=model.uploaded_by_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
            deleted_at=model.deleted_at,
        )
