"""Infrastructure-independent tariff catalog types."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class TariffRecord:
    """Public state of one immutable tariff version and its mutable metadata."""

    id: UUID
    original_filename: str
    internal_filename: str
    extension: str
    mime_type: str
    size: int
    sha256: str
    storage_key: str
    description: str | None
    notes: str | None
    active: bool
    version: int
    version_group_id: UUID
    previous_version_id: UUID | None
    uploaded_by_id: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
