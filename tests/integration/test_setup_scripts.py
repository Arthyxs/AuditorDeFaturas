"""Cross-platform setup script acceptance tests."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_SECRETS = {
    "INVOICE_AUDITOR_SETUP_IMAP_HOST": "imap.test.invalid",
    "INVOICE_AUDITOR_SETUP_IMAP_USER": "operator@test.invalid",
    "INVOICE_AUDITOR_SETUP_IMAP_PASSWORD": "imap-secret-never-log",
    "INVOICE_AUDITOR_SETUP_OPENAI_API_KEY": "ai-secret-never-log",
}


def read_env_value(path: Path, name: str) -> str:
    """Read a single dotenv value for acceptance assertions."""
    prefix = f"{name}="
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :]
    raise AssertionError(f"Missing {name} in generated environment file")


def assert_idempotent_and_redacted(command: list[str], environment_file: Path) -> None:
    """Run a setup script twice and verify stable, non-logged secrets."""
    environment = {**os.environ, **EXTERNAL_SECRETS}
    first = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    initial_app_secret = read_env_value(environment_file, "APP_SECRET_KEY")
    initial_postgres_secret = read_env_value(environment_file, "POSTGRES_PASSWORD")

    second = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert read_env_value(environment_file, "APP_SECRET_KEY") == initial_app_secret
    assert read_env_value(environment_file, "POSTGRES_PASSWORD") == initial_postgres_secret
    assert len(initial_app_secret) >= 64
    assert len(initial_postgres_secret) >= 64

    combined_output = first.stdout + first.stderr + second.stdout + second.stderr
    for secret in (
        initial_app_secret,
        initial_postgres_secret,
        *EXTERNAL_SECRETS.values(),
    ):
        assert secret not in combined_output

    if os.name == "nt":
        acl_script = (
            "$acl=Get-Acl -LiteralPath $env:INVOICE_AUDITOR_ACL_TEST_PATH; "
            "$current=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; "
            "$rules=@($acl.Access | ForEach-Object { "
            "$_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value "
            "}); "
            "[pscustomobject]@{Protected=$acl.AreAccessRulesProtected;"
            "Current=$current;Rules=$rules} "
            "| ConvertTo-Json -Compress"
        )
        inspected = subprocess.run(
            [command[0], "-NoProfile", "-Command", acl_script],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "INVOICE_AUDITOR_ACL_TEST_PATH": str(environment_file)},
        )
        import json

        acl = json.loads(inspected.stdout)
        allowed = {acl["Current"], "S-1-5-18", "S-1-5-32-544"}
        assert acl["Protected"] is True
        assert acl["Current"] in acl["Rules"]
        assert set(acl["Rules"]).issubset(allowed)
    else:
        assert stat.S_IMODE(environment_file.stat().st_mode) == 0o600


def test_powershell_setup_is_idempotent_with_space_in_path(tmp_path: Path) -> None:
    """The native Windows setup handles paths with spaces without exposing secrets."""
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        pytest.skip("PowerShell is unavailable")

    environment_file = tmp_path / "directory with spaces" / "invoice auditor.env"
    command = [
        executable,
        "-NoProfile",
        "-File",
        str(PROJECT_ROOT / "scripts" / "setup.ps1"),
        "-EnvironmentFile",
        str(environment_file),
        "-NonInteractive",
        "-SkipDocker",
    ]

    assert_idempotent_and_redacted(command, environment_file)


def test_linux_setup_is_idempotent_with_space_in_path(tmp_path: Path) -> None:
    """The Linux setup handles paths with spaces without exposing secrets."""
    if os.name == "nt":
        pytest.skip("Linux setup is exercised in a Linux container on Windows")

    executable = shutil.which("bash")
    if executable is None:
        pytest.skip("Bash is unavailable")

    environment_file = tmp_path / "directory with spaces" / "invoice auditor.env"
    command = [
        executable,
        (PROJECT_ROOT / "scripts" / "setup.sh").as_posix(),
        "--env-file",
        environment_file.as_posix(),
        "--non-interactive",
        "--skip-docker",
    ]

    assert_idempotent_and_redacted(command, environment_file)
