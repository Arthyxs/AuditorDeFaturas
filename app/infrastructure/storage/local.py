"""Immutable local filesystem implementation of the storage port."""

import json
import os
import re
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID, uuid4

from app.infrastructure.storage.validation import (
    UPLOAD_TYPES,
    UploadValidationError,
    UploadValidator,
    validate_original_filename,
)
from app.ports.storage import (
    PhysicalDeletionApproval,
    PhysicalDeletionDeniedError,
    StorageProvider,
    StoredFileIntegrityError,
    StoredFileMetadata,
    StoredFileNotFoundError,
)

_AREA_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_OBJECT_ID_PATTERN = re.compile(r"[0-9a-f]{32}\Z")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_CHUNK_SIZE = 1024 * 1024


class LocalStorageProvider(StorageProvider):
    """Publish validated file/metadata directories atomically under a configured root."""

    def __init__(
        self,
        root: Path,
        *,
        max_upload_size_bytes: int,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._root = self._root.resolve(strict=True)
        if not self._root.is_dir():
            raise ValueError("storage root must be a directory")
        self._validator = UploadValidator(max_upload_size_bytes)
        self._id_factory = id_factory

    def store(
        self, area: str, original_filename: str, mime_type: str, source: BinaryIO
    ) -> StoredFileMetadata:
        """Stream, validate and atomically publish an immutable object directory."""
        area_path = self._area_path(area)
        staging_parent = area_path / ".staging"
        staging_parent.mkdir(mode=0o700, exist_ok=True)
        self._assert_within_root(staging_parent)
        staging_path = Path(tempfile.mkdtemp(prefix="upload-", dir=staging_parent))
        payload_path = staging_path / "payload.tmp"

        try:
            digest, size = self._write_staged(payload_path, source)
            validated = self._validator.validate(
                payload_path,
                original_filename=original_filename,
                declared_mime=mime_type,
                size=size,
            )
            object_id = self._unique_object_id(area_path)
            key = f"{area}/{object_id}"
            internal_filename = f"{object_id}{validated.extension}"
            final_payload = staging_path / internal_filename
            payload_path.rename(final_payload)
            created_at = datetime.now(UTC)
            metadata = StoredFileMetadata(
                key=key,
                original_filename=validated.original_filename,
                internal_filename=internal_filename,
                extension=validated.extension,
                mime_type=validated.mime_type,
                size=size,
                sha256=digest,
                created_at=created_at,
            )
            self._write_metadata(staging_path / "metadata.json", metadata)
            final_payload.chmod(0o440)
            self._sync_directory(staging_path)

            final_path = area_path / object_id
            if final_path.exists():
                raise StoredFileIntegrityError("storage identifier collision")
            os.rename(staging_path, final_path)
            self._sync_directory(area_path)
            return metadata
        except BaseException:
            self._clean_staging(staging_path)
            raise

    def open_read(self, key: str) -> BinaryIO:
        """Verify metadata, size and SHA-256 before returning a read-only stream."""
        metadata = self.metadata(key)
        object_path = self._object_path(key)
        payload_path = self._payload_path(object_path, metadata)
        stored = payload_path.open("rb")
        try:
            digest = sha256()
            size = 0
            for chunk in iter(lambda: stored.read(_CHUNK_SIZE), b""):
                digest.update(chunk)
                size += len(chunk)
            if size != metadata.size or digest.hexdigest() != metadata.sha256:
                raise StoredFileIntegrityError("stored file does not match its integrity metadata")
            stored.seek(0)
            return stored
        except BaseException:
            stored.close()
            raise

    def metadata(self, key: str) -> StoredFileMetadata:
        """Load and strictly validate immutable sidecar metadata."""
        object_path = self._object_path(key)
        metadata_path = object_path / "metadata.json"
        self._assert_within_root(metadata_path)
        if not metadata_path.is_file():
            raise StoredFileNotFoundError("stored file metadata does not exist")
        try:
            raw: Any = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError
            metadata = StoredFileMetadata(
                key=str(raw["key"]),
                original_filename=str(raw["original_filename"]),
                internal_filename=str(raw["internal_filename"]),
                extension=str(raw["extension"]),
                mime_type=str(raw["mime_type"]),
                size=int(raw["size"]),
                sha256=str(raw["sha256"]),
                created_at=datetime.fromisoformat(str(raw["created_at"])),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise StoredFileIntegrityError("stored file metadata is invalid") from exc
        self._validate_metadata(metadata, key)
        return metadata

    def delete(self, key: str, *, approval: PhysicalDeletionApproval | None = None) -> None:
        """Deny deletion by default and remove only a cleared, explicitly approved object."""
        if approval is None or not approval.references_checked or not approval.reason.strip():
            raise PhysicalDeletionDeniedError(
                "physical deletion requires a reason and cleared reference check"
            )
        metadata = self.metadata(key)
        object_path = self._object_path(key)
        payload_path = self._payload_path(object_path, metadata)
        metadata_path = object_path / "metadata.json"
        if set(object_path.iterdir()) != {payload_path, metadata_path}:
            raise StoredFileIntegrityError("object directory contains unexpected entries")
        payload_path.chmod(0o600)
        metadata_path.chmod(0o600)
        payload_path.unlink()
        metadata_path.unlink()
        object_path.rmdir()
        self._sync_directory(object_path.parent)

    def _area_path(self, area: str) -> Path:
        if _AREA_PATTERN.fullmatch(area) is None:
            raise UploadValidationError("storage area is invalid")
        area_path = self._root / area
        area_path.mkdir(mode=0o750, exist_ok=True)
        self._assert_within_root(area_path)
        return area_path

    def _object_path(self, key: str) -> Path:
        if "\\" in key:
            raise StoredFileNotFoundError("storage key is invalid")
        parts = key.split("/")
        if (
            len(parts) != 2
            or _AREA_PATTERN.fullmatch(parts[0]) is None
            or _OBJECT_ID_PATTERN.fullmatch(parts[1]) is None
        ):
            raise StoredFileNotFoundError("storage key is invalid")
        object_path = self._root / parts[0] / parts[1]
        self._assert_within_root(object_path)
        if not object_path.is_dir():
            raise StoredFileNotFoundError("stored file does not exist")
        return object_path

    def _payload_path(self, object_path: Path, metadata: StoredFileMetadata) -> Path:
        payload_path = object_path / metadata.internal_filename
        self._assert_within_root(payload_path)
        if not payload_path.is_file():
            raise StoredFileIntegrityError("stored payload does not exist")
        return payload_path

    def _unique_object_id(self, area_path: Path) -> str:
        for _ in range(32):
            object_id = self._id_factory().hex
            if not (area_path / object_id).exists():
                return object_id
        raise StoredFileIntegrityError("unable to allocate a unique storage identifier")

    def _write_staged(self, path: Path, source: BinaryIO) -> tuple[str, int]:
        digest = sha256()
        size = 0
        with path.open("xb") as staged:
            while True:
                chunk = source.read(_CHUNK_SIZE)
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    raise TypeError("storage source must produce bytes")
                size += len(chunk)
                if size > self._validator.max_size_bytes:
                    raise UploadValidationError("file exceeds the configured size limit")
                digest.update(chunk)
                staged.write(chunk)
            staged.flush()
            os.fsync(staged.fileno())
        return digest.hexdigest(), size

    def _write_metadata(self, path: Path, metadata: StoredFileMetadata) -> None:
        serialized = json.dumps(
            {
                "key": metadata.key,
                "original_filename": metadata.original_filename,
                "internal_filename": metadata.internal_filename,
                "extension": metadata.extension,
                "mime_type": metadata.mime_type,
                "size": metadata.size,
                "sha256": metadata.sha256,
                "created_at": metadata.created_at.isoformat(),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        with path.open("xb") as sidecar:
            sidecar.write(serialized)
            sidecar.flush()
            os.fsync(sidecar.fileno())
        path.chmod(0o440)

    def _validate_metadata(self, metadata: StoredFileMetadata, key: str) -> None:
        object_id = key.split("/", maxsplit=1)[1]
        try:
            validate_original_filename(metadata.original_filename)
        except UploadValidationError as exc:
            raise StoredFileIntegrityError("stored original filename is invalid") from exc
        upload_type = UPLOAD_TYPES.get(metadata.extension)
        if (
            metadata.key != key
            or metadata.size < 1
            or _SHA256_PATTERN.fullmatch(metadata.sha256) is None
            or upload_type is None
            or Path(metadata.original_filename).suffix.casefold() != metadata.extension
            or metadata.mime_type != upload_type.canonical_mime
            or metadata.internal_filename != f"{object_id}{metadata.extension}"
            or metadata.created_at.tzinfo is None
        ):
            raise StoredFileIntegrityError("stored file metadata failed integrity validation")

    def _assert_within_root(self, path: Path) -> None:
        try:
            path.resolve().relative_to(self._root)
        except ValueError as exc:
            raise StoredFileIntegrityError("storage path escaped the configured root") from exc

    @staticmethod
    def _clean_staging(path: Path) -> None:
        if not path.exists():
            return
        for child in path.iterdir():
            if child.is_file():
                child.chmod(0o600)
                child.unlink()
        path.rmdir()

    @staticmethod
    def _sync_directory(path: Path) -> None:
        if os.name == "nt":
            return
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
