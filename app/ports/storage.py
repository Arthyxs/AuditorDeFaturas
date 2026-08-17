"""Replaceable immutable blob storage contract."""

from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Protocol


@dataclass(frozen=True)
class StoredFileMetadata:
    """Integrity and provenance metadata for one immutable stored file."""

    key: str
    original_filename: str
    internal_filename: str
    extension: str
    mime_type: str
    size: int
    sha256: str
    created_at: datetime
    content_kind: str = "validated_upload"


@dataclass(frozen=True)
class PhysicalDeletionApproval:
    """Explicit evidence required before irreversible deletion."""

    reason: str
    references_checked: bool


class StorageError(Exception):
    """Base error for storage contract failures."""


class StoredFileNotFoundError(StorageError):
    """The opaque storage key does not exist."""


class StoredFileIntegrityError(StorageError):
    """Persisted bytes or metadata no longer match their recorded integrity data."""


class PhysicalDeletionDeniedError(StorageError):
    """Irreversible deletion lacks explicit approval or reference clearance."""


class StorageProvider(Protocol):
    """Port for immutable file persistence independent of infrastructure."""

    def store(
        self, area: str, original_filename: str, mime_type: str, source: BinaryIO
    ) -> StoredFileMetadata:
        """Validate and atomically publish an immutable file."""

    def store_original(
        self, area: str, original_filename: str, mime_type: str, source: BinaryIO
    ) -> StoredFileMetadata:
        """Preserve exact untrusted original bytes without treating them as executable content."""

    def open_read(self, key: str) -> BinaryIO:
        """Open verified stored bytes for reading."""

    def metadata(self, key: str) -> StoredFileMetadata:
        """Read immutable file metadata."""

    def list_files(
        self, area: str, *, after: str | None = None, limit: int = 100
    ) -> tuple[StoredFileMetadata, ...]:
        """List immutable objects by portable area/key pagination."""

    def verify_hash(self, key: str, *, expected_sha256: str | None = None) -> str:
        """Recalculate a stored object's digest and optionally compare an expected digest."""

    def storage_reference(self, key: str) -> str:
        """Return a verified provider-opaque reference without exposing a filesystem path."""

    def delete(self, key: str, *, approval: PhysicalDeletionApproval | None = None) -> None:
        """Physically delete only with explicit approval and cleared references."""
