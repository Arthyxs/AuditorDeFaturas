"""M04 acceptance tests against a real PostgreSQL server."""

import os
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, Numeric, String, Table, create_engine, inspect, select, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.infrastructure.persistence.models import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.infrastructure.persistence.repositories import SqlAlchemyRepository
from app.infrastructure.persistence.session import (
    create_database_engine_from_url,
    create_session_factory,
    session_scope,
)
from app.infrastructure.persistence.types import PersistedEnum, string_enum_type
from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 with a disposable PostgreSQL server",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ProbeState(PersistedEnum):
    """Test-only enum proving the shared persistence convention."""

    NEW = "NEW"
    VERIFIED = "VERIFIED"


class PersistenceProbe(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Test-only table exercising M04 PostgreSQL conventions."""

    __tablename__ = "m04_persistence_probe"
    __table_args__ = (CheckConstraint("amount >= 0", name="amount_nonnegative"),)

    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    state: Mapped[ProbeState] = mapped_column(
        string_enum_type(ProbeState, name="m04_probe_state"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(nullable=False)


def render_url(url: URL) -> str:
    """Render a SQLAlchemy URL with its test password for driver use only."""
    return url.render_as_string(hide_password=False)


@pytest.fixture
def postgres_database_url() -> Iterator[str]:
    """Create and remove a uniquely named real PostgreSQL database."""
    configured_url = make_url(get_settings().database_url.get_secret_value())
    database_name = f"invoice_auditor_m04_{uuid4().hex}"
    admin_url = configured_url.set(database="postgres")
    test_url = configured_url.set(database=database_name)
    admin_engine = create_engine(render_url(admin_url), isolation_level="AUTOCOMMIT")

    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))

    try:
        yield render_url(test_url)
    finally:
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        admin_engine.dispose()


def alembic_config(database_url: str) -> Config:
    """Build an Alembic config with a disposable database override."""
    configuration = Config(str(PROJECT_ROOT / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return configuration


def current_revision(engine: Engine) -> str | None:
    """Read the database's current Alembic revision."""
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()


def test_upgrade_empty_database_to_head(postgres_database_url: str) -> None:
    """A brand-new PostgreSQL database upgrades to the M04 head revision."""
    configuration = alembic_config(postgres_database_url)
    command.upgrade(configuration, "head")
    engine = create_database_engine_from_url(postgres_database_url)
    try:
        assert current_revision(engine) == "20260817_0004"
    finally:
        engine.dispose()


def test_upgrade_from_previous_base_revision(postgres_database_url: str) -> None:
    """The base-to-head path remains repeatable after a downgrade."""
    configuration = alembic_config(postgres_database_url)
    command.upgrade(configuration, "head")
    command.downgrade(configuration, "base")
    command.upgrade(configuration, "head")
    engine = create_database_engine_from_url(postgres_database_url)
    try:
        assert current_revision(engine) == "20260817_0004"
    finally:
        engine.dispose()


def test_transactions_constraints_numeric_jsonb_and_utc(postgres_database_url: str) -> None:
    """The M04 session/repository/UoW foundation preserves PostgreSQL semantics."""
    command.upgrade(alembic_config(postgres_database_url), "head")
    engine = create_database_engine_from_url(postgres_database_url)
    probe_table = cast(Table, PersistenceProbe.__table__)
    probe_table.create(engine)
    session_factory = create_session_factory(engine)

    committed_id: UUID
    with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        repository = SqlAlchemyRepository(unit_of_work.session, PersistenceProbe)
        committed = PersistenceProbe(
            code="committed",
            state=ProbeState.VERIFIED,
            amount=Decimal("1234567890123.123456"),
            payload={"source": "m04", "valid": True},
        )
        repository.add(committed)
        unit_of_work.commit()
        committed_id = committed.id

    with (
        pytest.raises(RuntimeError, match="force rollback"),
        SqlAlchemyUnitOfWork(session_factory) as unit_of_work,
    ):
        SqlAlchemyRepository(unit_of_work.session, PersistenceProbe).add(
            PersistenceProbe(
                code="rolled-back",
                state=ProbeState.NEW,
                amount=Decimal("10.000001"),
                payload={},
            )
        )
        raise RuntimeError("force rollback")

    with session_factory() as session:
        repository = SqlAlchemyRepository(session, PersistenceProbe)
        loaded = repository.get(committed_id)
        assert loaded is not None
        assert loaded.amount == Decimal("1234567890123.123456")
        assert isinstance(loaded.amount, Decimal)
        assert loaded.payload == {"source": "m04", "valid": True}
        assert loaded.created_at.tzinfo is not None
        utc_offset = loaded.created_at.utcoffset()
        assert utc_offset is not None
        assert utc_offset.total_seconds() == 0
        assert (
            session.scalar(select(PersistenceProbe).where(PersistenceProbe.code == "rolled-back"))
            is None
        )

    with pytest.raises(IntegrityError), session_scope(session_factory) as session:
        session.add(
            PersistenceProbe(
                code="committed",
                state=ProbeState.NEW,
                amount=Decimal("1.000000"),
                payload={},
            )
        )

    with session_scope(session_factory) as session:
        session.add(
            PersistenceProbe(
                code="after-rollback",
                state=ProbeState.NEW,
                amount=Decimal("0.000001"),
                payload={"transaction": "usable"},
            )
        )

    database_inspector = inspect(engine)
    amount_column = next(
        column
        for column in database_inspector.get_columns(PersistenceProbe.__tablename__)
        if column["name"] == "amount"
    )
    amount_type = cast(Numeric[Decimal], amount_column["type"])
    assert amount_type.precision == 20
    assert amount_type.scale == 6
    constraint_names = {
        constraint["name"]
        for constraint in database_inspector.get_check_constraints(PersistenceProbe.__tablename__)
    }
    assert "ck_m04_persistence_probe_amount_nonnegative" in constraint_names
    assert "ck_m04_persistence_probe_m04_probe_state" in constraint_names

    probe_table.drop(engine)
    engine.dispose()
