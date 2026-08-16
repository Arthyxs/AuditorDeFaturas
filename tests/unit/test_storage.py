"""M06 immutable local storage and upload security tests."""

import io
import os
from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path
from stat import S_IXGRP, S_IXOTH, S_IXUSR
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.infrastructure.storage import LocalStorageProvider, UploadValidationError
from app.ports.storage import (
    PhysicalDeletionApproval,
    PhysicalDeletionDeniedError,
    StorageProvider,
    StoredFileIntegrityError,
    StoredFileNotFoundError,
)

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic" + b"\x00\x00\x00\x00IEND\xaeB`\x82"
JPEG = b"\xff\xd8\xff\xe0" + b"synthetic-jpeg" + b"\xff\xd9"
TIFF = b"II*\x00\x08\x00\x00\x00" + b"\x00" * 8
XLS = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504
CSV = b"document,amount\nCTE-1,10.00\n"


def xlsx_bytes() -> bytes:
    """Build a minimal structural XLSX ZIP for content validation."""
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("xl/workbook.xml", "<workbook />")
    return output.getvalue()


def xlsx_zip_bomb_bytes() -> bytes:
    """Build a tiny compressed archive with an unsafe expansion ratio."""
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("xl/workbook.xml", b"0" * (2 * 1024 * 1024))
    return output.getvalue()


def provider(root: Path, *, maximum: int = 1024 * 1024) -> LocalStorageProvider:
    return LocalStorageProvider(root, max_upload_size_bytes=maximum)


@pytest.mark.parametrize(
    ("filename", "mime_type", "content"),
    [
        ("invoice.pdf", "application/pdf", PDF),
        (
            "table.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            xlsx_bytes(),
        ),
        ("legacy.xls", "application/vnd.ms-excel", XLS),
        ("items.csv", "text/csv", CSV),
        ("scan.png", "image/png", PNG),
        ("photo.jpeg", "image/jpeg", JPEG),
        ("scan.tiff", "image/tiff", TIFF),
    ],
)
def test_approved_formats_store_read_and_hash(
    tmp_path: Path, filename: str, mime_type: str, content: bytes
) -> None:
    """Every approved type is stored under an internal name with verified metadata."""
    storage: StorageProvider = provider(tmp_path)
    metadata = storage.store("invoices", filename, mime_type, io.BytesIO(content))

    assert metadata.original_filename == filename
    assert metadata.internal_filename != filename
    assert metadata.internal_filename.startswith(metadata.key.split("/")[1])
    assert metadata.size == len(content)
    assert metadata.sha256 == sha256(content).hexdigest()
    assert metadata.created_at.tzinfo is not None
    with storage.open_read(metadata.key) as stored:
        assert stored.read() == content


def test_new_provider_instance_reads_existing_immutable_file(tmp_path: Path) -> None:
    """Metadata and bytes survive process/provider recreation."""
    first = provider(tmp_path)
    stored = first.store("tariffs", "rates.pdf", "application/pdf", io.BytesIO(PDF))

    restarted = provider(tmp_path)
    assert restarted.metadata(stored.key) == stored
    with restarted.open_read(stored.key) as stream:
        assert stream.read() == PDF


def test_identifier_collision_never_overwrites_existing_file(tmp_path: Path) -> None:
    """A generated identifier collision retries and preserves both objects."""
    first_id = UUID("11111111-1111-1111-1111-111111111111")
    second_id = UUID("22222222-2222-2222-2222-222222222222")
    identifiers: Iterator[UUID] = iter((first_id, first_id, second_id))
    storage = LocalStorageProvider(
        tmp_path, max_upload_size_bytes=1024, id_factory=lambda: next(identifiers)
    )

    first = storage.store("invoices", "first.pdf", "application/pdf", io.BytesIO(PDF))
    second = storage.store("invoices", "second.pdf", "application/pdf", io.BytesIO(PDF))

    assert first.key.endswith(first_id.hex)
    assert second.key.endswith(second_id.hex)
    with storage.open_read(first.key) as stream:
        assert stream.read() == PDF


class InterruptedStream:
    """Binary source that simulates a truncated/failed inbound stream."""

    def __init__(self) -> None:
        self._read = False

    def read(self, _: int = -1) -> bytes:
        if not self._read:
            self._read = True
            return PDF[:10]
        raise OSError("synthetic interrupted upload")


def test_interrupted_write_is_never_published(tmp_path: Path) -> None:
    """Atomic staging removes partial files when the input stream fails."""
    storage = provider(tmp_path)
    with pytest.raises(OSError, match="interrupted"):
        storage.store("invoices", "broken.pdf", "application/pdf", InterruptedStream())  # type: ignore[arg-type]

    published = [path for path in (tmp_path / "invoices").iterdir() if path.name != ".staging"]
    staged = list((tmp_path / "invoices" / ".staging").iterdir())
    assert published == []
    assert staged == []


@pytest.mark.parametrize(
    "filename",
    ["../invoice.pdf", "..\\invoice.pdf", "/tmp/invoice.pdf", "C:\\invoice.pdf", "a/b.pdf"],
)
def test_filename_path_traversal_is_rejected(tmp_path: Path, filename: str) -> None:
    storage = provider(tmp_path)
    with pytest.raises(UploadValidationError, match="path|separator"):
        storage.store("invoices", filename, "application/pdf", io.BytesIO(PDF))


@pytest.mark.parametrize("area", ["../outside", "a/b", "A", "", "."])
def test_area_path_traversal_is_rejected(tmp_path: Path, area: str) -> None:
    with pytest.raises(UploadValidationError, match="area"):
        provider(tmp_path).store(area, "invoice.pdf", "application/pdf", io.BytesIO(PDF))


@pytest.mark.parametrize("key", ["../outside", "invoices/../../x", "invoices\\x", "/absolute"])
def test_storage_key_path_traversal_is_rejected(tmp_path: Path, key: str) -> None:
    with pytest.raises(StoredFileNotFoundError, match="key"):
        provider(tmp_path).metadata(key)


def test_mime_extension_and_content_divergence_is_rejected(tmp_path: Path) -> None:
    storage = provider(tmp_path)
    with pytest.raises(UploadValidationError, match="MIME"):
        storage.store("invoices", "invoice.pdf", "image/png", io.BytesIO(PDF))
    with pytest.raises(UploadValidationError, match="complete PDF"):
        storage.store("invoices", "invoice.pdf", "application/pdf", io.BytesIO(PNG))
    with pytest.raises(UploadValidationError, match="complete PDF"):
        storage.store(
            "invoices", "truncated.pdf", "application/pdf", io.BytesIO(b"%PDF-1.4 no eof")
        )


def test_xlsx_unsafe_compression_ratio_is_rejected(tmp_path: Path) -> None:
    storage = provider(tmp_path)
    with pytest.raises(UploadValidationError, match="compression ratio"):
        storage.store(
            "invoices",
            "bomb.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            io.BytesIO(xlsx_zip_bomb_bytes()),
        )


def test_size_limit_stops_streaming_and_publishes_nothing(tmp_path: Path) -> None:
    storage = provider(tmp_path, maximum=8)
    with pytest.raises(UploadValidationError, match="size"):
        storage.store("invoices", "invoice.pdf", "application/pdf", io.BytesIO(PDF))
    assert not any(path.name != ".staging" for path in (tmp_path / "invoices").iterdir())


def test_corruption_after_storage_is_detected_before_read(tmp_path: Path) -> None:
    storage = provider(tmp_path)
    metadata = storage.store("invoices", "invoice.pdf", "application/pdf", io.BytesIO(PDF))
    payload = tmp_path / metadata.key / metadata.internal_filename
    payload.chmod(0o600)
    payload.write_bytes(PDF[:10])
    payload.chmod(0o440)

    with pytest.raises(StoredFileIntegrityError, match="integrity"):
        storage.open_read(metadata.key)


def test_physical_deletion_requires_explicit_reference_clearance(tmp_path: Path) -> None:
    storage = provider(tmp_path)
    metadata = storage.store("invoices", "invoice.pdf", "application/pdf", io.BytesIO(PDF))
    with pytest.raises(PhysicalDeletionDeniedError):
        storage.delete(metadata.key)
    with pytest.raises(PhysicalDeletionDeniedError):
        storage.delete(
            metadata.key,
            approval=PhysicalDeletionApproval(reason="test cleanup", references_checked=False),
        )

    storage.delete(
        metadata.key,
        approval=PhysicalDeletionApproval(reason="test cleanup", references_checked=True),
    )
    with pytest.raises(StoredFileNotFoundError):
        storage.metadata(metadata.key)


def test_uploaded_files_are_never_executable(tmp_path: Path) -> None:
    storage = provider(tmp_path)
    with pytest.raises(UploadValidationError, match="extension"):
        storage.store("invoices", "payload.exe", "application/octet-stream", io.BytesIO(b"MZ"))

    metadata = storage.store("invoices", "safe.csv", "text/csv", io.BytesIO(CSV))
    payload = tmp_path / metadata.key / metadata.internal_filename
    assert os.stat(payload).st_mode & (S_IXUSR | S_IXGRP | S_IXOTH) == 0
