"""Provider-neutral schemas returned by generic document inspection tools."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentToolError(Exception):
    """Explicit safe failure from an unsupported, corrupt or excessive read."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DocumentReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    file_id: str = Field(min_length=1, max_length=255)
    storage_key: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=255)


class EvidenceCoordinate(BaseModel):
    """Stable locator whose source hash makes later reproduction verifiable."""

    model_config = ConfigDict(frozen=True)

    file_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    kind: Literal["PDF", "SPREADSHEET", "IMAGE"]
    page: int | None = Field(default=None, ge=1)
    sheet: str | None = None
    cell_range: str | None = None
    bbox: tuple[str, str, str, str] | None = None
    pixel_box: tuple[int, int, int, int] | None = None


class PDFPage(BaseModel):
    page: int
    width: str
    height: str
    text_characters: int
    evidence: EvidenceCoordinate


class PDFPageList(BaseModel):
    pages: tuple[PDFPage, ...]


class PDFTextBlock(BaseModel):
    text: str
    evidence: EvidenceCoordinate


class PDFTextResult(BaseModel):
    blocks: tuple[PDFTextBlock, ...]


class PDFRenderResult(BaseModel):
    png_base64: str
    png_sha256: str
    width: int
    height: int
    evidence: EvidenceCoordinate


class SheetInfo(BaseModel):
    name: str
    max_row: int
    max_column: int
    evidence: EvidenceCoordinate


class SheetList(BaseModel):
    sheets: tuple[SheetInfo, ...]


class CellValue(BaseModel):
    coordinate: str
    value: str | None
    formula: str | None = None


class SheetRangeResult(BaseModel):
    sheet: str
    cell_range: str
    cells: tuple[CellValue, ...]
    evidence: EvidenceCoordinate


class CellSearchMatch(BaseModel):
    sheet: str
    coordinate: str
    value: str
    evidence: EvidenceCoordinate


class CellSearchResult(BaseModel):
    matches: tuple[CellSearchMatch, ...]


class ImageMetadataResult(BaseModel):
    format: str
    width: int
    height: int
    mode: str
    frames: int
    evidence: EvidenceCoordinate


class ImagePreviewResult(BaseModel):
    png_base64: str
    png_sha256: str
    width: int
    height: int
    evidence: EvidenceCoordinate
