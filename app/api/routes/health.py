"""Process liveness endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/health", tags=["health"])


class LivenessResponse(BaseModel):
    """Minimal response proving that the web process can serve requests."""

    status: str
    service: str


@router.get("/live", response_model=LivenessResponse)
def liveness() -> LivenessResponse:
    """Return process liveness without probing future dependencies."""
    return LivenessResponse(status="ok", service="app")
