"""M07 tariff catalog API acceptance tests."""

import io
import os
from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import xlwt  # type: ignore[import-untyped]
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook  # type: ignore[import-untyped]
from PIL import Image
from pypdf import PdfWriter
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

from app.config import Settings, get_settings
from app.infrastructure.persistence.models import TariffFile, User, UserRole
from app.infrastructure.persistence.session import create_session_factory
from app.infrastructure.security.passwords import hash_password
from app.main import create_app
from app.ports.storage import PhysicalDeletionDeniedError

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 with a disposable PostgreSQL server",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "https://invoice-auditor.test"
PASSWORD = "test-only-password-123"


def _pdf() -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)
    return output.getvalue()


def _xlsx() -> bytes:
    output = io.BytesIO()
    workbook = Workbook()
    workbook.active.append(["region", "price"])
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _xls() -> bytes:
    output = io.BytesIO()
    workbook = xlwt.Workbook()
    workbook.add_sheet("Tariff").write(0, 0, "price")
    workbook.save(output)
    return output.getvalue()


def _image(image_format: str) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (2, 2), color=(1, 2, 3)).save(output, format=image_format)
    return output.getvalue()


FORMATS = [
    ("rates.pdf", "application/pdf", _pdf()),
    (
        "rates.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        _xlsx(),
    ),
    ("rates.xls", "application/vnd.ms-excel", _xls()),
    ("rates.csv", "text/csv", b"region,price\nSouth,10.00\n"),
    ("rates.png", "image/png", _image("PNG")),
    ("rates.jpeg", "image/jpeg", _image("JPEG")),
    ("rates.tiff", "image/tiff", _image("TIFF")),
]


@pytest.fixture
def postgres_database_url() -> Iterator[str]:
    """Create an isolated M07 database migrated to current head."""
    configured_url = make_url(get_settings().database_url.get_secret_value())
    database_name = f"invoice_auditor_m07_{uuid4().hex}"
    admin_url = configured_url.set(database="postgres")
    test_url = configured_url.set(database=database_name)
    admin_engine = create_engine(
        admin_url.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    database_url = test_url.render_as_string(hide_password=False)
    configuration = Config(str(PROJECT_ROOT / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(configuration, "head")
    try:
        yield database_url
    finally:
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        admin_engine.dispose()


def _settings(database_url: str, storage_root: Path) -> Settings:
    return Settings.model_validate(
        {
            "app_env": "test",
            "app_base_url": ORIGIN,
            "app_secret_key": "test-app-secret-000000000000000000000000000",
            "first_admin_bootstrap_token": "test-bootstrap-token-000000000000000000000000",
            "postgres_password": "test-postgres-secret-00000000000000000000000",
            "database_url": database_url,
            "storage_root": storage_root,
        }
    )


def _app(database_url: str, storage_root: Path) -> FastAPI:
    application = create_app(_settings(database_url, storage_root))
    with create_session_factory(application.state.database_engine)() as database:
        for role in UserRole:
            database.add(
                User(
                    username=role.value.casefold(),
                    password_hash=hash_password(PASSWORD),
                    role=role,
                    is_active=True,
                )
            )
        database.commit()
    return application


def _login(client: TestClient, role: UserRole) -> None:
    response = client.post(
        "/api/auth/login",
        headers={"Origin": ORIGIN},
        json={"username": role.value.casefold(), "password": PASSWORD},
    )
    assert response.status_code == 200


def _upload(
    client: TestClient,
    filename: str = "rates.csv",
    mime_type: str = "text/csv",
    content: bytes = b"region,price\nSouth,10.00\n",
) -> dict[str, Any]:
    response = client.post(
        "/api/tariffs",
        headers={"Origin": ORIGIN},
        files=[("files", (filename, content, mime_type))],
        data={"description": "Current rates", "notes": "Synthetic fixture"},
    )
    assert response.status_code == 201, response.text
    return response.json()["items"][0]  # type: ignore[no-any-return]


def test_all_supported_formats_hash_download_and_duplicate_names(
    postgres_database_url: str, tmp_path: Path
) -> None:
    """All M06-supported formats enter the catalog without filename identity collisions."""
    application = _app(postgres_database_url, tmp_path)
    with TestClient(application, base_url=ORIGIN) as client:
        _login(client, UserRole.ADMIN)
        files = [("files", (name, content, mime)) for name, mime, content in FORMATS]
        response = client.post(
            "/api/tariffs",
            headers={"Origin": ORIGIN},
            files=files,
            data={"description": "Approved formats"},
        )
        assert response.status_code == 201, response.text
        items = response.json()["items"]
        assert len(items) == len(FORMATS)
        for item, (_, mime, content) in zip(items, FORMATS, strict=True):
            assert item["sha256"] == sha256(content).hexdigest()
            download = client.get(f"/api/tariffs/{item['id']}/download")
            assert download.status_code == 200
            assert download.headers["content-type"].startswith(mime)
            assert download.content == content

        first_duplicate = _upload(client, "same.csv")
        second_duplicate = _upload(client, "same.csv")
        assert first_duplicate["id"] != second_duplicate["id"]
        assert first_duplicate["original_filename"] == second_duplicate["original_filename"]
    application.state.database_engine.dispose()


def test_pagination_metadata_versioning_and_soft_delete_preserve_blobs(
    postgres_database_url: str, tmp_path: Path
) -> None:
    """Metadata changes and deletion never overwrite or remove immutable originals."""
    application = _app(postgres_database_url, tmp_path)
    with TestClient(application, base_url=ORIGIN) as client:
        _login(client, UserRole.OPERATOR)
        first = _upload(client, content=b"region,price\nNorth,20.00\n")
        original_download = client.get(f"/api/tariffs/{first['id']}/download").content
        updated = client.patch(
            f"/api/tariffs/{first['id']}",
            headers={"Origin": ORIGIN},
            json={"description": "Revised description", "active": False},
        )
        assert updated.status_code == 200
        assert updated.json()["description"] == "Revised description"
        assert updated.json()["sha256"] == first["sha256"]
        assert client.get(f"/api/tariffs/{first['id']}/download").content == original_download

        version_content = b"region,price\nNorth,21.00\n"
        version = client.post(
            f"/api/tariffs/{first['id']}/versions",
            headers={"Origin": ORIGIN},
            files={"file": ("rates-v2.csv", version_content, "text/csv")},
        )
        assert version.status_code == 201, version.text
        second = version.json()
        assert second["version"] == 2
        assert second["previous_version_id"] == first["id"]
        assert second["version_group_id"] == first["version_group_id"]
        assert client.get(f"/api/tariffs/{first['id']}/versions").json()[0]["id"] == first["id"]

        page = client.get("/api/tariffs?page=1&page_size=1")
        assert page.status_code == 200
        assert page.json()["page_size"] == 1
        assert page.json()["total"] == 2
        assert page.json()["pages"] == 2

        deleted = client.delete(f"/api/tariffs/{first['id']}", headers={"Origin": ORIGIN})
        assert deleted.status_code == 204
        assert client.get("/api/tariffs").json()["total"] == 1
        detail = client.get(f"/api/tariffs/{first['id']}").json()
        assert detail["deleted_at"] is not None
        assert client.get(f"/api/tariffs/{first['id']}/download").content == original_download

        with create_session_factory(application.state.database_engine)() as database:
            tariff = database.scalar(select(TariffFile).where(TariffFile.id == first["id"]))
            assert tariff is not None
            storage_key = tariff.storage_key
        with pytest.raises(PhysicalDeletionDeniedError):
            application.state.storage_provider.delete(storage_key)
    application.state.database_engine.dispose()


def test_tariff_api_rbac_validation_and_origin(postgres_database_url: str, tmp_path: Path) -> None:
    """Readers cannot mutate and every mutation keeps CSRF and upload validation."""
    application = _app(postgres_database_url, tmp_path)
    with TestClient(application, base_url=ORIGIN) as viewer:
        _login(viewer, UserRole.VIEWER)
        assert viewer.get("/api/tariffs").status_code == 200
        denied = viewer.post(
            "/api/tariffs",
            headers={"Origin": ORIGIN},
            files={"files": ("rates.csv", b"a,b\n1,2\n", "text/csv")},
        )
        assert denied.status_code == 403

    with TestClient(application, base_url=ORIGIN) as operator:
        _login(operator, UserRole.OPERATOR)
        missing_origin = operator.post(
            "/api/tariffs",
            files={"files": ("rates.csv", b"a,b\n1,2\n", "text/csv")},
        )
        assert missing_origin.status_code == 403
        invalid = operator.post(
            "/api/tariffs",
            headers={"Origin": ORIGIN},
            files={"files": ("payload.exe", b"MZ", "application/octet-stream")},
        )
        assert invalid.status_code == 422
        assert "extension" in invalid.json()["detail"]
    application.state.database_engine.dispose()
