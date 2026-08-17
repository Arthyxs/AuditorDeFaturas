"""Smoke tests for the executable backend skeleton."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app, create_app


def test_application_is_importable() -> None:
    """The ASGI entry point exposes a configured FastAPI application."""
    assert isinstance(app, FastAPI)
    assert app.title == "InvoiceAuditor"


def test_application_factory_creates_independent_instances() -> None:
    """The factory supports isolated application instances in future tests."""
    first = create_app()
    second = create_app()

    assert first is not second
    assert first.version == "0.1.0"


def test_compiled_spa_is_served_without_shadowing_api(tmp_path: Path) -> None:
    """Production serves the SPA shell and preserves API/static 404 semantics."""
    frontend = tmp_path / "dist"
    (frontend / "assets").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<!doctype html><html><body><div id="root">InvoiceAuditor</div></body></html>',
        encoding="utf-8",
    )
    (frontend / "assets" / "app.js").write_text("window.invoiceAuditor = true", encoding="utf-8")
    client = TestClient(create_app(frontend_directory=frontend))

    for route in ("/", "/login"):
        response = client.get(route)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert '<div id="root">InvoiceAuditor</div>' in response.text

    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/api/health/live").json() == {"status": "ok", "service": "app"}
    unknown_api = client.get("/api/not-a-real-endpoint")
    assert unknown_api.status_code == 404
    assert not unknown_api.headers["content-type"].startswith("text/html")
