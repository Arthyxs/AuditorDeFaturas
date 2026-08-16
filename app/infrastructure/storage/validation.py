"""Content-aware validation for untrusted uploaded documents."""

from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Literal
from zipfile import BadZipFile, ZipFile


class UploadValidationError(ValueError):
    """An upload violates the approved filename, type or size policy."""


@dataclass(frozen=True)
class UploadType:
    """Approved extension, declared MIME and canonical stored MIME."""

    declared_mimes: frozenset[str]
    canonical_mime: str


UPLOAD_TYPES: dict[str, UploadType] = {
    ".pdf": UploadType(frozenset({"application/pdf"}), "application/pdf"),
    ".xlsx": UploadType(
        frozenset({"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    ".xls": UploadType(frozenset({"application/vnd.ms-excel"}), "application/vnd.ms-excel"),
    ".csv": UploadType(frozenset({"text/csv", "application/csv"}), "text/csv"),
    ".png": UploadType(frozenset({"image/png"}), "image/png"),
    ".jpg": UploadType(frozenset({"image/jpeg"}), "image/jpeg"),
    ".jpeg": UploadType(frozenset({"image/jpeg"}), "image/jpeg"),
    ".tif": UploadType(frozenset({"image/tiff"}), "image/tiff"),
    ".tiff": UploadType(frozenset({"image/tiff"}), "image/tiff"),
}


@dataclass(frozen=True)
class ValidatedUpload:
    """Normalized metadata after filename, MIME and content validation."""

    original_filename: str
    extension: str
    mime_type: str


class UploadValidator:
    """Validate untrusted uploads without executing or extracting their content."""

    def __init__(self, max_size_bytes: int) -> None:
        if max_size_bytes < 1:
            raise ValueError("max_size_bytes must be positive")
        self.max_size_bytes = max_size_bytes

    def validate(
        self, path: Path, *, original_filename: str, declared_mime: str, size: int
    ) -> ValidatedUpload:
        """Validate metadata and inspect the staged bytes against their extension."""
        filename = validate_original_filename(original_filename)
        if size < 1:
            raise UploadValidationError("empty files are not accepted")
        if size > self.max_size_bytes:
            raise UploadValidationError("file exceeds the configured size limit")
        if path.stat().st_size != size:
            raise UploadValidationError("staged file size changed during validation")

        extension = Path(filename).suffix.casefold()
        upload_type = UPLOAD_TYPES.get(extension)
        if upload_type is None:
            raise UploadValidationError("file extension is not supported")
        normalized_mime = declared_mime.partition(";")[0].strip().casefold()
        if normalized_mime not in upload_type.declared_mimes:
            raise UploadValidationError("declared MIME does not match the file extension")

        _validate_content(path, extension, size)
        return ValidatedUpload(
            original_filename=filename,
            extension=extension,
            mime_type=upload_type.canonical_mime,
        )


def validate_original_filename(filename: str) -> str:
    """Reject traversal, absolute paths, control characters and ambiguous names."""
    if not filename or len(filename) > 255:
        raise UploadValidationError("filename must contain 1-255 characters")
    if filename in {".", ".."} or filename != PurePath(filename).name:
        raise UploadValidationError("filename must not contain a path")
    if "/" in filename or "\\" in filename or ":" in filename:
        raise UploadValidationError("filename must not contain path separators")
    if any(ord(character) < 32 or ord(character) == 127 for character in filename):
        raise UploadValidationError("filename contains control characters")
    return filename


def _validate_content(path: Path, extension: str, size: int) -> None:
    with path.open("rb") as uploaded:
        prefix = uploaded.read(16)
        uploaded.seek(max(0, size - 2048))
        suffix = uploaded.read(2048)

    if extension == ".pdf":
        if not prefix.startswith(b"%PDF-") or b"%%EOF" not in suffix:
            raise UploadValidationError("content is not a complete PDF")
    elif extension == ".png":
        if prefix[:8] != b"\x89PNG\r\n\x1a\n" or b"IEND" not in suffix[-32:]:
            raise UploadValidationError("content is not a complete PNG")
    elif extension in {".jpg", ".jpeg"}:
        if not prefix.startswith(b"\xff\xd8\xff") or not suffix.endswith(b"\xff\xd9"):
            raise UploadValidationError("content is not a complete JPEG")
    elif extension in {".tif", ".tiff"}:
        _validate_tiff(prefix, size)
    elif extension == ".xls":
        if not prefix.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") or size < 512:
            raise UploadValidationError("content is not an OLE spreadsheet")
    elif extension == ".xlsx":
        _validate_xlsx(path)
    elif extension == ".csv":
        _validate_csv(path)


def _validate_tiff(prefix: bytes, size: int) -> None:
    if len(prefix) < 8 or prefix[:4] not in {b"II*\x00", b"MM\x00*"}:
        raise UploadValidationError("content is not a TIFF image")
    byte_order: Literal["little", "big"] = "little" if prefix[:2] == b"II" else "big"
    first_ifd = int.from_bytes(prefix[4:8], byte_order)
    if first_ifd < 8 or first_ifd >= size:
        raise UploadValidationError("TIFF directory offset is invalid")


def _validate_xlsx(path: Path) -> None:
    try:
        with ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) > 10_000:
                raise UploadValidationError("spreadsheet contains too many archive entries")
            if sum(entry.file_size for entry in archive.infolist()) > 256 * 1024 * 1024:
                raise UploadValidationError("spreadsheet expands beyond the safe limit")
            if any(
                entry.compress_size > 0 and entry.file_size > entry.compress_size * 100
                for entry in archive.infolist()
            ):
                raise UploadValidationError("spreadsheet archive compression ratio is unsafe")
            if "[Content_Types].xml" not in names or not any(
                name.startswith("xl/") for name in names
            ):
                raise UploadValidationError("ZIP content is not an XLSX spreadsheet")
            if archive.testzip() is not None:
                raise UploadValidationError("spreadsheet archive is corrupt")
    except BadZipFile as exc:
        raise UploadValidationError("content is not an XLSX spreadsheet") from exc


def _validate_csv(path: Path) -> None:
    with path.open("rb") as csv_file:
        for chunk in iter(lambda: csv_file.read(1024 * 1024), b""):
            if b"\x00" in chunk:
                raise UploadValidationError("CSV contains binary null bytes")
            text = chunk.decode("latin-1")
            if any(ord(character) < 32 and character not in "\t\r\n" for character in text):
                raise UploadValidationError("CSV contains binary control characters")
