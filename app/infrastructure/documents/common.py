"""Shared immutable-source checks for document tools."""

from io import BytesIO

from app.infrastructure.documents.models import DocumentReference, DocumentToolError
from app.ports.storage import StorageProvider


def verified_bytes(
    storage: StorageProvider, reference: DocumentReference, *, max_bytes: int
) -> bytes:
    metadata = storage.metadata(reference.storage_key)
    if metadata.sha256 != reference.sha256:
        raise DocumentToolError(
            "DOCUMENT_INTEGRITY_ERROR", "document hash does not match reference"
        )
    if metadata.size > max_bytes:
        raise DocumentToolError("DOCUMENT_LIMIT", "document exceeds inspection size limit")
    with storage.open_read(reference.storage_key) as source:
        payload = source.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise DocumentToolError("DOCUMENT_LIMIT", "document exceeds inspection size limit")
    return payload


def byte_stream(payload: bytes) -> BytesIO:
    return BytesIO(payload)
