"""Filesystem heartbeat used by the container worker health check."""

import time
from pathlib import Path

DEFAULT_HEARTBEAT_PATH = Path("/tmp/invoice-auditor-worker.heartbeat")
DEFAULT_MAX_AGE_SECONDS = 20.0


def write_heartbeat(path: Path = DEFAULT_HEARTBEAT_PATH) -> None:
    """Atomically publish a worker heartbeat timestamp."""
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(str(time.time()), encoding="utf-8")
    temporary_path.replace(path)


def heartbeat_is_fresh(
    path: Path = DEFAULT_HEARTBEAT_PATH,
    *,
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
    now: float | None = None,
) -> bool:
    """Return whether a readable heartbeat is recent enough."""
    try:
        heartbeat_time = float(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False

    current_time = time.time() if now is None else now
    age = current_time - heartbeat_time
    return 0.0 <= age <= max_age_seconds
