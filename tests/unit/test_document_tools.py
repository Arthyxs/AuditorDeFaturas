# mypy: disable-error-code="no-untyped-call"

from io import BytesIO
from pathlib import Path

import openpyxl  # type: ignore[import-untyped]
import pymupdf
import pytest
import xlwt  # type: ignore[import-untyped]
from PIL import Image

from app.infrastructure.documents import (
    DocumentReference,
    DocumentToolError,
    ImageTools,
    PDFTools,
    SpreadsheetTools,
)
from app.infrastructure.storage.local import LocalStorageProvider


def stored_reference(
    tmp_path: Path, *, filename: str, mime_type: str, payload: bytes
) -> tuple[LocalStorageProvider, DocumentReference]:
    storage = LocalStorageProvider(tmp_path / "data", max_upload_size_bytes=5_000_000)
    metadata = storage.store("tariffs", filename, mime_type, BytesIO(payload))
    return storage, DocumentReference(
        file_id="fixture-1",
        storage_key=metadata.key,
        sha256=metadata.sha256,
        filename=metadata.original_filename,
        mime_type=metadata.mime_type,
    )


def pdf_bytes() -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=300, height=200)
    page.insert_text((30, 50), "Tarifa Vale do Aco - faixa 501 a 1000 kg")
    payload = bytes(document.tobytes())
    document.close()
    return payload


def test_pdf_tools_return_reproducible_page_and_bbox_coordinates(tmp_path: Path) -> None:
    storage, reference = stored_reference(
        tmp_path, filename="tarifa.pdf", mime_type="application/pdf", payload=pdf_bytes()
    )
    tools = PDFTools(storage)

    pages = tools.list_pages(reference)
    text = tools.extract_text(reference, start_page=1, end_page=1)
    matches = tools.search_text(reference, query="501 a 1000")
    rendered = tools.render_page(reference, page=1)

    assert pages.pages[0].evidence.page == 1
    assert text.blocks[0].evidence.sha256 == reference.sha256
    assert text.blocks[0].evidence.bbox is not None
    assert matches.blocks[0].evidence.bbox is not None
    assert rendered.evidence.page == 1
    assert rendered.png_sha256 and rendered.width == 300


def xlsx_bytes() -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Regioes"
    sheet.append(["Cidade", "Regiao", "Valor"])
    sheet.append(["Ipatinga", "4", "=10+2"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def xls_bytes() -> bytes:
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Legacy")
    sheet.write(0, 0, "CTE")
    sheet.write(1, 0, "82918")
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


@pytest.mark.parametrize(
    ("filename", "mime_type", "payload", "sheet", "query"),
    [
        (
            "tarifa.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            xlsx_bytes(),
            "Regioes",
            "Ipatinga",
        ),
        (
            "tarifa.csv",
            "text/csv",
            "Cidade;Regiao\nIpatinga;4\n".encode("cp1252"),
            "Sheet1",
            "Ipatinga",
        ),
        ("tarifa.xls", "application/vnd.ms-excel", xls_bytes(), "Legacy", "82918"),
    ],
)
def test_spreadsheet_formats_preserve_sheet_and_cell_evidence(
    tmp_path: Path,
    filename: str,
    mime_type: str,
    payload: bytes,
    sheet: str,
    query: str,
) -> None:
    storage, reference = stored_reference(
        tmp_path, filename=filename, mime_type=mime_type, payload=payload
    )
    tools = SpreadsheetTools(storage)
    listed = tools.list_sheets(reference)
    match = tools.search_cells(reference, query=query).matches[0]
    cell = tools.read_range(reference, sheet_name=sheet, cell_range=match.coordinate)

    assert listed.sheets[0].evidence.sheet == sheet
    assert match.evidence.cell_range == match.coordinate
    assert cell.evidence.sha256 == reference.sha256


def test_xlsx_formula_is_returned_without_execution(tmp_path: Path) -> None:
    storage, reference = stored_reference(
        tmp_path,
        filename="tarifa.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        payload=xlsx_bytes(),
    )
    result = SpreadsheetTools(storage).read_range(
        reference, sheet_name="Regioes", cell_range="C2:C2"
    )
    assert result.cells[0].value == "=10+2"
    assert result.cells[0].formula == "=10+2"


@pytest.mark.parametrize(("filename", "format"), [("foto.png", "PNG"), ("scan.tiff", "TIFF")])
def test_image_metadata_and_preview_are_bounded_and_reproducible(
    tmp_path: Path, filename: str, format: str
) -> None:
    image = Image.new("RGB", (120, 80), "white")
    output = BytesIO()
    image.save(output, format=format)
    mime = "image/png" if format == "PNG" else "image/tiff"
    storage, reference = stored_reference(
        tmp_path, filename=filename, mime_type=mime, payload=output.getvalue()
    )
    tools = ImageTools(storage, max_preview_side=60)

    metadata = tools.metadata(reference)
    preview = tools.preview(reference)

    assert metadata.evidence.pixel_box == (0, 0, 120, 80)
    assert preview.width == 60
    assert preview.evidence.sha256 == reference.sha256


def test_corrupt_unsupported_and_excessive_documents_fail_explicitly(tmp_path: Path) -> None:
    storage = LocalStorageProvider(tmp_path / "data", max_upload_size_bytes=5_000_000)
    metadata = storage.store_original(
        "tariffs", "bad.pdf", "application/pdf", BytesIO(b"%PDF-1.4\ninvalid")
    )
    reference = DocumentReference(
        file_id="fixture-bad",
        storage_key=metadata.key,
        sha256=metadata.sha256,
        filename=metadata.original_filename,
        mime_type=metadata.mime_type,
    )
    with pytest.raises(DocumentToolError, match="could not be opened") as corrupt:
        PDFTools(storage).list_pages(reference)
    assert corrupt.value.code == "DOCUMENT_CORRUPT"

    with pytest.raises(DocumentToolError) as excessive:
        PDFTools(storage, max_file_bytes=2).list_pages(reference)
    assert excessive.value.code == "DOCUMENT_LIMIT"

    unsupported = reference.model_copy(
        update={"filename": "file.doc", "mime_type": "application/msword"}
    )
    with pytest.raises(DocumentToolError) as unsupported_error:
        SpreadsheetTools(storage).list_sheets(unsupported)
    assert unsupported_error.value.code == "DOCUMENT_UNSUPPORTED"
