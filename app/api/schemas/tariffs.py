"""HTTP schemas for tariff catalog management."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TariffResponse(BaseModel):
    """Public metadata for one immutable tariff version."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    internal_filename: str
    extension: str
    mime_type: str
    size: int
    sha256: str
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
    usage_count: int = 0


class TariffListResponse(BaseModel):
    """Required page envelope for tariff listing."""

    items: list[TariffResponse]
    page: int
    page_size: int
    total: int
    pages: int


class TariffUpdateRequest(BaseModel):
    """Mutable catalog fields; immutable blob fields are intentionally absent."""

    description: str | None = Field(default=None, max_length=4000)
    notes: str | None = Field(default=None, max_length=4000)
    active: bool | None = None


class TariffUploadResponse(BaseModel):
    """Result of a multi-file upload."""

    items: list[TariffResponse]
