"""Smoke tests for the executable backend skeleton."""

from fastapi import FastAPI

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
