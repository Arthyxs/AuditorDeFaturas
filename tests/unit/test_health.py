"""Tests for M02 process health primitives."""

from pathlib import Path

from app.api.routes.health import liveness
from app.worker.heartbeat import heartbeat_is_fresh


def test_liveness_reports_the_web_process() -> None:
    """The liveness endpoint has a stable, dependency-free payload."""
    response = liveness()

    assert response.status == "ok"
    assert response.service == "app"


def test_worker_heartbeat_must_exist_and_be_fresh(tmp_path: Path) -> None:
    """A missing, stale or future heartbeat never reports healthy."""
    heartbeat = tmp_path / "worker.heartbeat"

    assert not heartbeat_is_fresh(heartbeat, now=100.0)

    heartbeat.write_text("80", encoding="utf-8")
    assert heartbeat_is_fresh(heartbeat, max_age_seconds=20.0, now=100.0)

    heartbeat.write_text("79.999", encoding="utf-8")
    assert not heartbeat_is_fresh(heartbeat, max_age_seconds=20.0, now=100.0)

    heartbeat.write_text("101", encoding="utf-8")
    assert not heartbeat_is_fresh(heartbeat, now=100.0)
