"""Typed application settings and secret-safe configuration access."""

from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    """Supported runtime environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Validated settings loaded from environment variables or a local `.env` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: AppEnvironment = AppEnvironment.PRODUCTION
    app_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")
    app_timezone: str = "America/Sao_Paulo"
    app_secret_key: SecretStr

    postgres_db: str = "invoice_auditor"
    postgres_user: str = "invoice_auditor"
    postgres_password: SecretStr
    database_url: SecretStr

    imap_host: str = ""
    imap_port: int = Field(default=993, ge=1, le=65535)
    imap_ssl: bool = True
    imap_user: str = ""
    imap_password: SecretStr | None = None
    imap_inbox: str = "INBOX"
    imap_folder_invoices: str = "Faturas"
    imap_folder_due_notices: str = "Avisos"
    imap_folder_general: str = "Gerais"
    imap_folder_review: str = "Revisao"

    worker_enabled: bool = True
    email_check_interval_minutes: int = Field(default=60, ge=1)
    email_process_batch_size: int = Field(default=50, ge=1)

    ai_email_provider: str = "openai"
    ai_email_model: str = "gpt-5.6-luna"
    ai_tariff_selector_provider: str = "openai"
    ai_tariff_selector_model: str = "gpt-5.6-terra"
    ai_audit_provider: str = "openai"
    ai_audit_model: str = "gpt-5.6-terra"
    ai_advanced_provider: str = "openai"
    ai_advanced_model: str = "gpt-5.6-sol"

    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    google_ai_api_key: SecretStr | None = None

    storage_provider: str = "local"
    storage_root: Path = Path("/app/data")

    audit_absolute_tolerance: Decimal = Decimal("0.01")
    audit_percent_tolerance: Decimal = Decimal("0")

    backup_enabled: bool = True
    backup_retention_days: int = Field(default=30, ge=1)

    @field_validator("app_secret_key", "postgres_password")
    @classmethod
    def validate_internal_secret(cls, value: SecretStr) -> SecretStr:
        """Reject missing, placeholder or weak internal secrets."""
        secret = value.get_secret_value()
        if len(secret) < 32:
            raise ValueError("internal secrets must contain at least 32 characters")
        if secret.strip().upper() in {"CHANGE_ME", "CHANGEME"}:
            raise ValueError("placeholder secrets are not allowed")
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        """Require the approved PostgreSQL SQLAlchemy driver URL."""
        database_url = value.get_secret_value()
        if not database_url.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg")
        if "CHANGE_ME" in database_url.upper():
            raise ValueError("DATABASE_URL contains a placeholder secret")
        return value

    @field_validator("app_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Reject unknown IANA timezone identifiers."""
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("APP_TIMEZONE must be a valid IANA timezone") from exc
        return value

    def safe_summary(self) -> dict[str, Any]:
        """Expose operational configuration without secret values."""
        return {
            "app_env": self.app_env.value,
            "app_base_url": str(self.app_base_url),
            "app_timezone": self.app_timezone,
            "postgres_db": self.postgres_db,
            "postgres_user": self.postgres_user,
            "database_configured": bool(self.database_url.get_secret_value()),
            "worker_enabled": self.worker_enabled,
            "storage_provider": self.storage_provider,
            "storage_root": str(self.storage_root),
        }


@lru_cache
def get_settings() -> Settings:
    """Load and cache the process configuration."""
    return Settings()  # type: ignore[call-arg]
