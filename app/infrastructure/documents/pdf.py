# mypy: disable-error-code="no-untyped-call"
"""Generic bounded PDF tools with page and rectangle evidence."""

import base64
from hashlib import sha256

import pymupdf

from app.infrastructure.documents.common import verified_bytes
from app.infrastructure.documents.models import (
    DocumentReference,
    DocumentToolError,
    EvidenceCoordinate,
    PDFPage,
    PDFPageList,
    PDFRenderResult,
    PDFTextBlock,
    PDFTextResult,
)
from app.ports.storage import StorageProvider


def _decimal(value: float) -> str:
    return f"{value:.3f}"


class PDFTools:
    def __init__(
        self,
        storage: StorageProvider,
        *,
        max_file_bytes: int = 50 * 1024 * 1024,
        max_pages_per_call: int = 25,
        max_text_characters: int = 200_000,
        max_render_pixels: int = 16_000_000,
    ) -> None:
        self._storage = storage
        self._max_file_bytes = max_file_bytes
        self._max_pages = max_pages_per_call
        self._max_text = max_text_characters
        self._max_pixels = max_render_pixels

    def _open(self, reference: DocumentReference) -> pymupdf.Document:
        if reference.mime_type != "application/pdf" and not reference.filename.casefold().endswith(
            ".pdf"
        ):
            raise DocumentToolError("DOCUMENT_UNSUPPORTED", "document is not a PDF")
        payload = verified_bytes(self._storage, reference, max_bytes=self._max_file_bytes)
        try:
            document = pymupdf.open(stream=payload, filetype="pdf")
            if document.needs_pass:
                document.close()
                raise DocumentToolError("DOCUMENT_UNSUPPORTED", "encrypted PDF is unsupported")
            return document
        except DocumentToolError:
            raise
        except Exception as exc:
            raise DocumentToolError("DOCUMENT_CORRUPT", "PDF could not be opened") from exc

    @staticmethod
    def _evidence(
        reference: DocumentReference,
        page: int,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> EvidenceCoordinate:
        return EvidenceCoordinate(
            file_id=reference.file_id,
            sha256=reference.sha256,
            kind="PDF",
            page=page,
            bbox=(
                (_decimal(bbox[0]), _decimal(bbox[1]), _decimal(bbox[2]), _decimal(bbox[3]))
                if bbox
                else None
            ),
        )

    def list_pages(self, reference: DocumentReference) -> PDFPageList:
        with self._open(reference) as document:
            if document.page_count > self._max_pages:
                raise DocumentToolError("DOCUMENT_LIMIT", "PDF page listing exceeds call limit")
            return PDFPageList(
                pages=tuple(
                    PDFPage(
                        page=index + 1,
                        width=_decimal(page.rect.width),
                        height=_decimal(page.rect.height),
                        text_characters=len(page.get_text("text")),
                        evidence=self._evidence(reference, index + 1),
                    )
                    for index, page in enumerate(document)
                )
            )

    def extract_text(
        self, reference: DocumentReference, *, start_page: int, end_page: int
    ) -> PDFTextResult:
        if start_page < 1 or end_page < start_page or end_page - start_page + 1 > self._max_pages:
            raise DocumentToolError("DOCUMENT_LIMIT", "invalid or excessive PDF page range")
        blocks: list[PDFTextBlock] = []
        characters = 0
        with self._open(reference) as document:
            if end_page > document.page_count:
                raise DocumentToolError("DOCUMENT_RANGE_ERROR", "PDF page is out of range")
            for page_number in range(start_page, end_page + 1):
                page = document[page_number - 1]
                for raw in page.get_text("blocks", sort=True):
                    text = str(raw[4]).strip()
                    if not text:
                        continue
                    characters += len(text)
                    if characters > self._max_text:
                        raise DocumentToolError("DOCUMENT_LIMIT", "PDF text exceeds call limit")
                    bbox = (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
                    blocks.append(
                        PDFTextBlock(
                            text=text, evidence=self._evidence(reference, page_number, bbox)
                        )
                    )
        return PDFTextResult(blocks=tuple(blocks))

    def search_text(
        self, reference: DocumentReference, *, query: str, max_matches: int = 50
    ) -> PDFTextResult:
        if not query.strip() or not 1 <= max_matches <= 100:
            raise DocumentToolError("DOCUMENT_LIMIT", "invalid PDF search limits")
        matches: list[PDFTextBlock] = []
        with self._open(reference) as document:
            if document.page_count > self._max_pages:
                raise DocumentToolError("DOCUMENT_LIMIT", "PDF search exceeds page limit")
            for index, page in enumerate(document):
                for rectangle in page.search_for(query):
                    matches.append(
                        PDFTextBlock(
                            text=page.get_textbox(rectangle).strip() or query,
                            evidence=self._evidence(
                                reference,
                                index + 1,
                                (rectangle.x0, rectangle.y0, rectangle.x1, rectangle.y1),
                            ),
                        )
                    )
                    if len(matches) >= max_matches:
                        return PDFTextResult(blocks=tuple(matches))
        return PDFTextResult(blocks=tuple(matches))

    def render_page(
        self, reference: DocumentReference, *, page: int, scale: str = "1"
    ) -> PDFRenderResult:
        try:
            zoom = int(scale)
        except ValueError as exc:
            raise DocumentToolError(
                "DOCUMENT_LIMIT", "PDF render scale must be an integer"
            ) from exc
        if page < 1 or zoom not in {1, 2, 3}:
            raise DocumentToolError("DOCUMENT_LIMIT", "invalid PDF render parameters")
        with self._open(reference) as document:
            if page > document.page_count:
                raise DocumentToolError("DOCUMENT_RANGE_ERROR", "PDF page is out of range")
            selected = document[page - 1]
            width = round(selected.rect.width * zoom)
            height = round(selected.rect.height * zoom)
            if width * height > self._max_pixels:
                raise DocumentToolError("DOCUMENT_LIMIT", "rendered PDF exceeds pixel limit")
            payload = selected.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).tobytes(
                "png"
            )
        return PDFRenderResult(
            png_base64=base64.b64encode(payload).decode("ascii"),
            png_sha256=sha256(payload).hexdigest(),
            width=width,
            height=height,
            evidence=self._evidence(reference, page),
        )
