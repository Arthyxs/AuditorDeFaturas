"""FastAPI application entry point."""

from fastapi import FastAPI

from app import __version__
from app.api.routes.health import router as health_router
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the web application from validated process settings."""
    resolved_settings = get_settings() if settings is None else settings
    application = FastAPI(title="InvoiceAuditor", version=__version__)
    application.state.settings = resolved_settings
    application.include_router(health_router)
    return application


app = create_app()
