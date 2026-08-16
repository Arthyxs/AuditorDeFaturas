"""Minimal long-running worker process for the canonical runtime."""

import time

from app.worker.heartbeat import write_heartbeat

HEARTBEAT_INTERVAL_SECONDS = 5.0


def run() -> None:
    """Keep the worker process alive and publish its process heartbeat.

    Durable scheduling and business jobs intentionally begin in later milestones.
    """
    while True:
        write_heartbeat()
        time.sleep(HEARTBEAT_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
