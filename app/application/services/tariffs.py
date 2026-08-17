"""Infrastructure-independent tariff catalog use cases."""

from typing import BinaryIO
from uuid import UUID

from app.domain.tariffs.models import TariffRecord
from app.ports.storage import PhysicalDeletionApproval, StorageProvider, StoredFileMetadata
from app.ports.tariffs import TariffCatalogRepository


class TariffNotFoundError(Exception):
    """Requested tariff metadata does not exist."""


class TariffVersionConflictError(Exception):
    """A version can only be appended to the current end of a lineage."""


class TariffService:
    """Coordinate immutable storage through replaceable persistence ports."""

    def __init__(self, repository: TariffCatalogRepository, storage: StorageProvider) -> None:
        self._repository = repository
        self._storage = storage

    def upload(
        self,
        *,
        filename: str,
        mime_type: str,
        source: BinaryIO,
        uploaded_by_id: UUID,
        description: str | None = None,
        notes: str | None = None,
    ) -> TariffRecord:
        stored = self._storage.store("tariffs", filename, mime_type, source)
        try:
            return self._repository.create(
                stored,
                uploaded_by_id=uploaded_by_id,
                description=description,
                notes=notes,
            )
        except BaseException:
            self._remove_unreferenced_upload(stored)
            raise

    def upload_version(
        self,
        tariff_id: UUID,
        *,
        filename: str,
        mime_type: str,
        source: BinaryIO,
        uploaded_by_id: UUID,
        description: str | None = None,
        notes: str | None = None,
    ) -> TariffRecord:
        previous = self._repository.get(tariff_id, lock=True)
        if previous is None or previous.deleted_at is not None:
            raise TariffNotFoundError
        if self._repository.successor_exists(previous.id):
            raise TariffVersionConflictError
        stored = self._storage.store("tariffs", filename, mime_type, source)
        try:
            return self._repository.create_version(
                previous,
                stored,
                uploaded_by_id=uploaded_by_id,
                description=description if description is not None else previous.description,
                notes=notes if notes is not None else previous.notes,
            )
        except BaseException:
            self._remove_unreferenced_upload(stored)
            raise

    def get(self, tariff_id: UUID) -> TariffRecord:
        tariff = self._repository.get(tariff_id)
        if tariff is None:
            raise TariffNotFoundError
        return tariff

    def update(
        self,
        tariff_id: UUID,
        *,
        description: str | None,
        notes: str | None,
        active: bool | None,
        supplied_fields: set[str],
    ) -> TariffRecord:
        tariff = self._repository.update_metadata(
            tariff_id,
            description=description,
            notes=notes,
            active=active,
            supplied_fields=supplied_fields,
        )
        if tariff is None:
            raise TariffNotFoundError
        return tariff

    def soft_delete(self, tariff_id: UUID) -> None:
        if not self._repository.soft_delete(tariff_id):
            raise TariffNotFoundError

    def _remove_unreferenced_upload(self, stored: StoredFileMetadata) -> None:
        self._storage.delete(
            stored.key,
            approval=PhysicalDeletionApproval(
                reason="compensate failed tariff catalog transaction",
                references_checked=True,
            ),
        )

    def compensate_uncommitted_upload(self, storage_key: str) -> None:
        """Remove a blob after its surrounding database transaction was rolled back."""
        self._remove_unreferenced_upload(self._storage.metadata(storage_key))
