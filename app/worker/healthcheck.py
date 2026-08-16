"""Container health check for the worker process."""

from app.worker.heartbeat import heartbeat_is_fresh


def main() -> int:
    """Return a process status suitable for Docker health checks."""
    return 0 if heartbeat_is_fresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
