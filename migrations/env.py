"""Alembic environment bound to the application PostgreSQL configuration."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app.config import get_settings
from app.infrastructure.persistence.models import Base
from app.infrastructure.persistence.session import create_database_engine_from_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def configured_database_url() -> str:
    """Prefer a test/CLI override and otherwise use secret-safe app settings."""
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url:
        return configured_url
    return get_settings().database_url.get_secret_value()


def run_migrations_offline() -> None:
    """Run migrations without creating an Engine."""
    context.configure(
        url=configured_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def configure_connection(connection: Connection) -> None:
    """Run migrations in one transaction on an existing connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        transaction_per_migration=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against PostgreSQL using the application engine policy."""
    connectable = create_database_engine_from_url(configured_database_url())
    try:
        with connectable.connect() as connection:
            configure_connection(connection)
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
