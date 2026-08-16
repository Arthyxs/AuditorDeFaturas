"""FastAPI application entry point."""

from fastapi import FastAPI

from app import __version__


def create_app() -> FastAPI:
    """Create the web application without infrastructure side effects."""
    return FastAPI(title="InvoiceAuditor", version=__version__)


app = create_app()
