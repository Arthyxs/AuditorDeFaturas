"""Tests for typed and secret-safe M03 settings."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.config import AppEnvironment, Settings

VALID_SETTINGS = {
    "app_env": "test",
    "app_secret_key": "app-secret-00000000000000000000000000000000",
    "first_admin_bootstrap_token": "bootstrap-secret-0000000000000000000000000000",
    "postgres_password": "postgres-secret-000000000000000000000000000",
    "database_url": "postgresql+psycopg://invoice_auditor:secret@postgres:5432/invoice_auditor",
}


def build_settings(**overrides: str) -> Settings:
    """Build settings without consulting the repository `.env` file."""
    values = {**VALID_SETTINGS, **overrides}
    return Settings.model_validate(values)


def test_valid_settings_are_typed() -> None:
    """Environment strings become the approved runtime types."""
    settings = build_settings(
        app_env="development",
        imap_ssl="false",
        email_process_batch_size="75",
        upload_max_size_bytes="1048576",
        audit_absolute_tolerance="0.005",
    )

    assert settings.app_env is AppEnvironment.DEVELOPMENT
    assert settings.imap_ssl is False
    assert settings.email_process_batch_size == 75
    assert settings.upload_max_size_bytes == 1048576
    assert settings.audit_absolute_tolerance == Decimal("0.005")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("app_env", "staging"),
        ("app_timezone", "Not/A_Timezone"),
        ("app_secret_key", "short"),
        ("app_secret_key", "CHANGE_ME"),
        ("first_admin_bootstrap_token", "short"),
        ("postgres_password", "short"),
        ("database_url", "sqlite:///invoice-auditor.db"),
        ("database_url", "postgresql+psycopg://user:CHANGE_ME@postgres/db"),
        ("imap_port", "70000"),
        ("email_check_interval_minutes", "0"),
        ("backup_retention_days", "0"),
        ("upload_max_size_bytes", "0"),
    ],
)
def test_invalid_configuration_is_rejected(key: str, value: str) -> None:
    """Unsafe and nonsensical values fail before the process starts."""
    with pytest.raises(ValidationError):
        build_settings(**{key: value})


@pytest.mark.parametrize(
    "missing_key",
    ["app_secret_key", "first_admin_bootstrap_token", "postgres_password", "database_url"],
)
def test_required_internal_configuration_cannot_be_absent(missing_key: str) -> None:
    """Internal secrets and the database URL are mandatory."""
    values = {**VALID_SETTINGS, missing_key: ""}

    with pytest.raises(ValidationError):
        Settings.model_validate(values)


def test_secret_values_are_redacted_from_representations_and_summary() -> None:
    """Secret-bearing settings never expose their values through normal diagnostics."""
    settings = build_settings()
    rendered = repr(settings)
    summary = str(settings.safe_summary())

    for secret in (
        VALID_SETTINGS["app_secret_key"],
        VALID_SETTINGS["first_admin_bootstrap_token"],
        VALID_SETTINGS["postgres_password"],
        VALID_SETTINGS["database_url"],
    ):
        assert secret not in rendered
        assert secret not in summary

    assert "**********" in rendered
