"""Minimal long-running worker process for the canonical runtime."""

import time

from app.config import Settings, get_settings
from app.worker.heartbeat import write_heartbeat

HEARTBEAT_INTERVAL_SECONDS = 5.0


def run(settings: Settings | None = None) -> None:
    """Keep the worker process alive and publish its process heartbeat.

    Durable scheduling and business jobs intentionally begin in later milestones.
    """
    resolved_settings = get_settings() if settings is None else settings
    if not resolved_settings.worker_enabled:
        return

    while True:
        write_heartbeat()
        time.sleep(HEARTBEAT_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
