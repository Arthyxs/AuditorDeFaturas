"""M06 persistence test across real container recreation."""

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


def test_file_survives_app_container_recreation() -> None:
    """A synthetic file in the bind-mounted area remains readable after recreation."""
    provider_code = (
        "s=get_settings(); "
        "p=LocalStorageProvider(s.storage_root,"
        "max_upload_size_bytes=s.upload_max_size_bytes); "
    )
    create_code = (
        "import io; from app.config import get_settings; "
        "from app.infrastructure.storage.local import LocalStorageProvider; "
        + provider_code
        + "m=p.store('invoices','container-test.pdf','application/pdf',"
        "io.BytesIO(b'%PDF-1.4\\n%%EOF')); "
        "print(m.key)"
    )
    created = compose("exec", "-T", "app", "python", "-c", create_code)
    key = created.stdout.strip().splitlines()[-1]
    assert key.startswith("invoices/")

    try:
        compose("up", "-d", "--force-recreate", "--wait", "--wait-timeout", "120", "app")
        read_code = (
            "from app.config import get_settings; "
            "from app.infrastructure.storage.local import LocalStorageProvider; "
            + provider_code
            + f"f=p.open_read('{key}'); print(f.read().decode()); f.close()"
        )
        loaded = compose("exec", "-T", "app", "python", "-c", read_code)
        assert loaded.stdout.strip().splitlines()[-2:] == ["%PDF-1.4", "%%EOF"]
    finally:
        delete_code = (
            "from app.config import get_settings; "
            "from app.infrastructure.storage.local import LocalStorageProvider; "
            "from app.ports.storage import PhysicalDeletionApproval; "
            + provider_code
            + f"p.delete('{key}',approval=PhysicalDeletionApproval("
            "reason='test cleanup',references_checked=True))"
        )
        compose("exec", "-T", "app", "python", "-c", delete_code)
