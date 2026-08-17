"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

from app import __version__
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.config import Settings, get_settings
from app.infrastructure.persistence.session import create_database_engine, create_session_factory


class SPAStaticFiles(StaticFiles):
    """Serve the compiled frontend with a safe history fallback outside ``/api``."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        normalized_path = path.lstrip("/")
        is_spa_route = not normalized_path.startswith("api/") and Path(path).suffix == ""
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404 and is_spa_route:
                return await super().get_response("index.html", scope)
            raise
        if response.status_code == 404 and is_spa_route:
            return await super().get_response("index.html", scope)
        return response


def create_app(
    settings: Settings | None = None, *, frontend_directory: Path | None = None
) -> FastAPI:
    """Create the web application from validated process settings."""
    resolved_settings = get_settings() if settings is None else settings
    application = FastAPI(title="InvoiceAuditor", version=__version__)
    application.state.settings = resolved_settings
    application.state.database_engine = create_database_engine(resolved_settings)
    application.state.session_factory = create_session_factory(application.state.database_engine)
    application.include_router(auth_router)
    application.include_router(health_router)
    static_directory = (
        Path(__file__).resolve().parents[1] / "frontend" / "dist"
        if frontend_directory is None
        else frontend_directory
    )
    if static_directory.is_dir():
        frontend = SPAStaticFiles(directory=static_directory, html=True)

        async def serve_frontend(request: Request) -> Response:
            """Delegate the final catch-all route to the compiled frontend."""
            return await frontend.get_response(
                str(request.path_params["frontend_path"]), request.scope
            )

        application.add_api_route(
            "/{frontend_path:path}",
            serve_frontend,
            methods=["GET", "HEAD"],
            include_in_schema=False,
        )
    return application


app = create_app()
