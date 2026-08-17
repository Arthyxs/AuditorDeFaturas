"""Replaceable tariff catalog persistence contract."""

from typing import Protocol
from uuid import UUID

from app.domain.tariffs.models import TariffRecord
from app.ports.storage import StoredFileMetadata


class TariffCatalogRepository(Protocol):
    """Persistence operations required by tariff use cases."""

    def create(
        self,
        stored: StoredFileMetadata,
        *,
        uploaded_by_id: UUID,
        description: str | None,
        notes: str | None,
    ) -> TariffRecord: ...

    def create_version(
        self,
        previous: TariffRecord,
        stored: StoredFileMetadata,
        *,
        uploaded_by_id: UUID,
        description: str | None,
        notes: str | None,
    ) -> TariffRecord: ...

    def get(self, tariff_id: UUID, *, lock: bool = False) -> TariffRecord | None: ...

    def successor_exists(self, tariff_id: UUID) -> bool: ...

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        active: bool | None,
        include_deleted: bool,
        search: str | None,
    ) -> tuple[list[TariffRecord], int]: ...

    def versions(self, group_id: UUID) -> list[TariffRecord]: ...

    def update_metadata(
        self,
        tariff_id: UUID,
        *,
        description: str | None,
        notes: str | None,
        active: bool | None,
        supplied_fields: set[str],
    ) -> TariffRecord | None: ...

    def soft_delete(self, tariff_id: UUID) -> bool: ...
