"""Strict AI tool-call schemas for generic document inspection."""

from pydantic import BaseModel, Field

from app.infrastructure.documents.image import ImageTools
from app.infrastructure.documents.models import DocumentReference
from app.infrastructure.documents.pdf import PDFTools
from app.infrastructure.documents.spreadsheet import SpreadsheetTools
from app.ports.ai import AITool


class PDFPagesInput(BaseModel):
    document: DocumentReference


class PDFTextInput(BaseModel):
    document: DocumentReference
    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)


class PDFSearchInput(BaseModel):
    document: DocumentReference
    query: str = Field(min_length=1, max_length=500)
    max_matches: int = Field(default=50, ge=1, le=100)


class PDFRenderInput(BaseModel):
    document: DocumentReference
    page: int = Field(ge=1)
    scale: str = Field(default="1", pattern=r"^[123]$")


class SheetListInput(BaseModel):
    document: DocumentReference


class SheetRangeInput(BaseModel):
    document: DocumentReference
    sheet_name: str = Field(min_length=1, max_length=255)
    cell_range: str = Field(min_length=2, max_length=64)


class SheetSearchInput(BaseModel):
    document: DocumentReference
    query: str = Field(min_length=1, max_length=500)
    max_matches: int = Field(default=50, ge=1, le=100)


class ImageInput(BaseModel):
    document: DocumentReference


class DocumentAITools:
    """Expose only allowlisted, typed and bounded document operations."""

    def __init__(self, pdf: PDFTools, spreadsheet: SpreadsheetTools, image: ImageTools) -> None:
        self._pdf = pdf
        self._spreadsheet = spreadsheet
        self._image = image

    def definitions(self) -> tuple[AITool, ...]:
        return (
            AITool(
                "list_pdf_pages", "List PDF pages and dimensions.", PDFPagesInput, self.pdf_pages
            ),
            AITool(
                "extract_pdf_text", "Extract bounded PDF text blocks.", PDFTextInput, self.pdf_text
            ),
            AITool(
                "search_pdf_text",
                "Search PDF text with rectangles.",
                PDFSearchInput,
                self.pdf_search,
            ),
            AITool(
                "render_pdf_page", "Render one PDF page as PNG.", PDFRenderInput, self.pdf_render
            ),
            AITool(
                "list_sheets",
                "List spreadsheet sheets and dimensions.",
                SheetListInput,
                self.sheets,
            ),
            AITool(
                "read_range", "Read a bounded spreadsheet range.", SheetRangeInput, self.sheet_range
            ),
            AITool(
                "search_cells", "Search spreadsheet cells.", SheetSearchInput, self.sheet_search
            ),
            AITool("image_metadata", "Read image metadata.", ImageInput, self.image_metadata),
            AITool(
                "image_preview", "Render a bounded image preview.", ImageInput, self.image_preview
            ),
        )

    def pdf_pages(self, value: BaseModel) -> dict[str, object]:
        request = PDFPagesInput.model_validate(value)
        return self._pdf.list_pages(request.document).model_dump(mode="json")

    def pdf_text(self, value: BaseModel) -> dict[str, object]:
        request = PDFTextInput.model_validate(value)
        return self._pdf.extract_text(
            request.document, start_page=request.start_page, end_page=request.end_page
        ).model_dump(mode="json")

    def pdf_search(self, value: BaseModel) -> dict[str, object]:
        request = PDFSearchInput.model_validate(value)
        return self._pdf.search_text(
            request.document, query=request.query, max_matches=request.max_matches
        ).model_dump(mode="json")

    def pdf_render(self, value: BaseModel) -> dict[str, object]:
        request = PDFRenderInput.model_validate(value)
        return self._pdf.render_page(
            request.document, page=request.page, scale=request.scale
        ).model_dump(mode="json")

    def sheets(self, value: BaseModel) -> dict[str, object]:
        request = SheetListInput.model_validate(value)
        return self._spreadsheet.list_sheets(request.document).model_dump(mode="json")

    def sheet_range(self, value: BaseModel) -> dict[str, object]:
        request = SheetRangeInput.model_validate(value)
        return self._spreadsheet.read_range(
            request.document, sheet_name=request.sheet_name, cell_range=request.cell_range
        ).model_dump(mode="json")

    def sheet_search(self, value: BaseModel) -> dict[str, object]:
        request = SheetSearchInput.model_validate(value)
        return self._spreadsheet.search_cells(
            request.document, query=request.query, max_matches=request.max_matches
        ).model_dump(mode="json")

    def image_metadata(self, value: BaseModel) -> dict[str, object]:
        request = ImageInput.model_validate(value)
        return self._image.metadata(request.document).model_dump(mode="json")

    def image_preview(self, value: BaseModel) -> dict[str, object]:
        request = ImageInput.model_validate(value)
        return self._image.preview(request.document).model_dump(mode="json")
