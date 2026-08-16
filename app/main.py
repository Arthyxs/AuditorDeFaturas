"""FastAPI application entry point."""

from fastapi import FastAPI

from app import __version__
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.config import Settings, get_settings
from app.infrastructure.persistence.session import create_database_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the web application from validated process settings."""
    resolved_settings = get_settings() if settings is None else settings
    application = FastAPI(title="InvoiceAuditor", version=__version__)
    application.state.settings = resolved_settings
    application.state.database_engine = create_database_engine(resolved_settings)
    application.state.session_factory = create_session_factory(application.state.database_engine)
    application.include_router(auth_router)
    application.include_router(health_router)
    return application


app = create_app()
