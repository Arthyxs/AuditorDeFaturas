"""FastAPI application entry point."""

from fastapi import FastAPI

from app import __version__
from app.api.routes.health import router as health_router


def create_app() -> FastAPI:
    """Create the web application without infrastructure side effects."""
    application = FastAPI(title="InvoiceAuditor", version=__version__)
    application.include_router(health_router)
    return application


app = create_app()
