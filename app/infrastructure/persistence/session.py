"""SQLAlchemy engine and transactional session factories."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings

SessionFactory = sessionmaker[Session]


def create_database_engine(settings: Settings | None = None) -> Engine:
    """Create a PostgreSQL engine from redacted settings."""
    resolved_settings = get_settings() if settings is None else settings
    return create_database_engine_from_url(resolved_settings.database_url.get_secret_value())


def create_database_engine_from_url(database_url: str) -> Engine:
    """Create a PostgreSQL engine that always presents timestamps in UTC."""
    return create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=UTC"},
    )


def create_session_factory(engine: Engine) -> SessionFactory:
    """Create sessions with explicit transaction boundaries."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: SessionFactory) -> Iterator[Session]:
    """Commit on success and roll back before re-raising any failure."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
