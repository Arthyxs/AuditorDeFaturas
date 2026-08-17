"""Bounded image metadata and preview tools without OCR or business parsing."""

import base64
import warnings
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.infrastructure.documents.common import verified_bytes
from app.infrastructure.documents.models import (
    DocumentReference,
    DocumentToolError,
    EvidenceCoordinate,
    ImageMetadataResult,
    ImagePreviewResult,
)
from app.ports.storage import StorageProvider

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


class ImageTools:
    def __init__(
        self,
        storage: StorageProvider,
        *,
        max_file_bytes: int = 50 * 1024 * 1024,
        max_source_pixels: int = 40_000_000,
        max_preview_side: int = 1600,
    ) -> None:
        self._storage = storage
        self._max_file_bytes = max_file_bytes
        self._max_source_pixels = max_source_pixels
        self._max_preview_side = max_preview_side

    @staticmethod
    def _evidence(reference: DocumentReference, width: int, height: int) -> EvidenceCoordinate:
        return EvidenceCoordinate(
            file_id=reference.file_id,
            sha256=reference.sha256,
            kind="IMAGE",
            pixel_box=(0, 0, width, height),
        )

    def _open(self, reference: DocumentReference) -> Image.Image:
        if Path(reference.filename).suffix.casefold() not in _IMAGE_EXTENSIONS:
            raise DocumentToolError("DOCUMENT_UNSUPPORTED", "image format is unsupported")
        payload = verified_bytes(self._storage, reference, max_bytes=self._max_file_bytes)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(BytesIO(payload))
                if image.width * image.height > self._max_source_pixels:
                    image.close()
                    raise DocumentToolError("DOCUMENT_LIMIT", "image exceeds pixel limit")
                image.load()
                return image
        except DocumentToolError:
            raise
        except (UnidentifiedImageError, OSError, Image.DecompressionBombWarning) as exc:
            raise DocumentToolError("DOCUMENT_CORRUPT", "image could not be opened") from exc

    def metadata(self, reference: DocumentReference) -> ImageMetadataResult:
        with self._open(reference) as image:
            return ImageMetadataResult(
                format=image.format or "UNKNOWN",
                width=image.width,
                height=image.height,
                mode=image.mode,
                frames=getattr(image, "n_frames", 1),
                evidence=self._evidence(reference, image.width, image.height),
            )

    def preview(self, reference: DocumentReference) -> ImagePreviewResult:
        with self._open(reference) as image:
            original_width, original_height = image.size
            rendered = image.convert("RGB")
            rendered.thumbnail((self._max_preview_side, self._max_preview_side))
            output = BytesIO()
            rendered.save(output, format="PNG", optimize=False)
            payload = output.getvalue()
            return ImagePreviewResult(
                png_base64=base64.b64encode(payload).decode("ascii"),
                png_sha256=sha256(payload).hexdigest(),
                width=rendered.width,
                height=rendered.height,
                evidence=self._evidence(reference, original_width, original_height),
            )
