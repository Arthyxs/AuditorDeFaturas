"""M06 persistence test across real container recreation."""

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DOCKER_STORAGE_INTEGRATION") != "1",
    reason="set RUN_DOCKER_STORAGE_INTEGRATION=1 with the canonical Compose runtime",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def compose(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run canonical Compose without invoking a shell."""
    return subprocess.run(
        ["docker", "compose", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_every_accepted_area_survives_app_container_recreation() -> None:
    """The mounted storage root persists arbitrary accepted areas across recreation."""
    provider_code = (
        "s=get_settings(); "
        "p=LocalStorageProvider(s.storage_root,"
        "max_upload_size_bytes=s.upload_max_size_bytes); "
    )
    create_code = (
        "import io,json; from app.config import get_settings; "
        "from app.infrastructure.storage.local import LocalStorageProvider; "
        + provider_code
        + "areas=('tariffs','invoices','reports','backups','emails','attachments'); "
        "items=[p.store(a,'container-test.csv','text/csv',"
        "io.BytesIO(b'document,amount\\nCTE-1,10.00\\n')) for a in areas]; "
        "print(json.dumps([m.key for m in items]))"
    )
    created = compose("exec", "-T", "app", "python", "-c", create_code)
    keys = json.loads(created.stdout.strip().splitlines()[-1])
    assert [key.split("/", maxsplit=1)[0] for key in keys] == [
        "tariffs",
        "invoices",
        "reports",
        "backups",
        "emails",
        "attachments",
    ]

    try:
        compose("up", "-d", "--force-recreate", "--wait", "--wait-timeout", "120", "app")
        read_code = (
            "import json; from app.config import get_settings; "
            "from app.infrastructure.storage.local import LocalStorageProvider; "
            + provider_code
            + f"keys={keys!r}; "
            "print(json.dumps([p.open_read(key).read().decode() for key in keys]))"
        )
        loaded = compose("exec", "-T", "app", "python", "-c", read_code)
        contents = json.loads(loaded.stdout.strip().splitlines()[-1])
        assert contents == ["document,amount\nCTE-1,10.00\n"] * len(keys)
    finally:
        delete_code = (
            "from app.config import get_settings; "
            "from app.infrastructure.storage.local import LocalStorageProvider; "
            "from app.ports.storage import PhysicalDeletionApproval; "
            + provider_code
            + f"keys={keys!r}; "
            "approval=PhysicalDeletionApproval(reason='test cleanup',references_checked=True); "
            "[p.delete(key,approval=approval) for key in keys]"
        )
        compose("exec", "-T", "app", "python", "-c", delete_code)


def test_spa_is_served_from_canonical_container_origin() -> None:
    """The canonical app origin exposes the compiled React shell and auth API."""
    import urllib.request

    with urllib.request.urlopen("http://127.0.0.1:8000/", timeout=5) as response:
        body = response.read().decode("utf-8")
        assert response.status == 200
        assert response.headers.get_content_type() == "text/html"
        assert '<div id="root"></div>' in body

    with urllib.request.urlopen(
        "http://127.0.0.1:8000/api/auth/bootstrap/status", timeout=5
    ) as response:
        assert response.status == 200
        assert response.headers.get_content_type() == "application/json"
