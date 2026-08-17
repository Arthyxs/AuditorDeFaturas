"""M12 provider fake, versioned pricing and immutable AI telemetry acceptance tests."""

import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine, make_url

from app.application.services.ai import AIExecutionService, AIProviderRouter
from app.config import get_settings
from app.infrastructure.ai.fake_provider import ScriptedAIProvider
from app.infrastructure.persistence.models import AICall
from app.infrastructure.persistence.repositories import PostgreSQLAITelemetryRepository
from app.infrastructure.persistence.session import create_session_factory
from app.ports.ai import (
    AIMessage,
    AIPrompt,
    AIRequest,
    AIResult,
    AITask,
    AITimeoutError,
    AIUsage,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 with a disposable PostgreSQL server",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ContractOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]


@pytest.fixture
def database_url() -> Iterator[str]:
    configured = make_url(get_settings().database_url.get_secret_value())
    database_name = f"invoice_auditor_m12_{uuid4().hex}"
    admin_url = configured.set(database="postgres")
    test_url = configured.set(database=database_name)
    admin = create_engine(
        admin_url.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    value = test_url.render_as_string(hide_password=False)
    alembic = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic.set_main_option("sqlalchemy.url", value.replace("%", "%%"))
    command.upgrade(alembic, "head")
    try:
        yield value
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    value = create_engine(database_url)
    try:
        yield value
    finally:
        value.dispose()


def _sequence(values: list[Any]) -> Callable[[], Any]:
    iterator = iter(values)
    return lambda: next(iterator)


def _request() -> AIRequest:
    return AIRequest(
        task=AITask.PROVIDER_CONTRACT,
        prompt=AIPrompt("provider_contract", "1", "c" * 64, "Return status."),
        messages=(AIMessage("user", "health"),),
        output_model=ContractOutput,
    )


def test_fake_provider_records_tokens_cache_cost_prompt_latency_and_status(engine: Engine) -> None:
    repository = PostgreSQLAITelemetryRepository(create_session_factory(engine))
    start = datetime(2026, 8, 17, 12, tzinfo=UTC)
    price = repository.add_price(
        provider="openai",
        model="configured-model",
        version="2026-08-17",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        effective_to=None,
        input_per_million=Decimal("2.00"),
        cached_input_per_million=Decimal("0.50"),
        output_per_million=Decimal("10.00"),
    )
    with pytest.raises(ValueError, match="overlap"):
        repository.add_price(
            provider="openai",
            model="configured-model",
            version="overlap",
            effective_from=datetime(2026, 6, 1, tzinfo=UTC),
            effective_to=None,
            input_per_million=Decimal("1"),
            cached_input_per_million=Decimal("1"),
            output_per_million=Decimal("1"),
        )

    result = AIResult(
        output=ContractOutput(status="ok"),
        provider_request_id="provider-request-1",
        usage=AIUsage(input_tokens=1000, cached_input_tokens=200, output_tokens=100),
        tool_rounds=1,
        tool_calls=2,
    )
    fake = ScriptedAIProvider([result])
    service = AIExecutionService(
        router=AIProviderRouter({"openai": fake}),
        telemetry=repository,
        now=_sequence([start, start]),
        timer=_sequence([10.0, 10.125]),
    )
    executed = service.execute(
        provider="OpenAI",
        model="configured-model",
        request=_request(),
    )

    assert executed.result.output == ContractOutput(status="ok")
    assert executed.estimated_cost == Decimal("0.00270000")
    assert executed.currency == "USD"
    assert fake.calls[0][0] == "configured-model"
    with create_session_factory(engine)() as database:
        call = database.get(AICall, executed.call_id)
        assert call is not None
        assert call.provider == "openai"
        assert call.model == "configured-model"
        assert call.task == AITask.PROVIDER_CONTRACT.value
        assert call.provider_request_id == "provider-request-1"
        assert call.duration_ms == 125
        assert (call.input_tokens, call.cached_input_tokens, call.output_tokens) == (1000, 200, 100)
        assert call.estimated_cost == Decimal("0.00270000")
        assert call.price_version_id == price.id
        assert call.prompt_name == "provider_contract"
        assert call.prompt_version == "1"
        assert call.prompt_hash == "c" * 64
        assert call.status == "SUCCEEDED"
        assert call.error_code is None
        assert (call.tool_rounds, call.tool_calls) == (1, 2)


def test_provider_error_is_recorded_without_fake_success(engine: Engine) -> None:
    repository = PostgreSQLAITelemetryRepository(create_session_factory(engine))
    start = datetime(2026, 8, 17, 13, tzinfo=UTC)
    service = AIExecutionService(
        router=AIProviderRouter({"openai": ScriptedAIProvider([AITimeoutError()])}),
        telemetry=repository,
        now=_sequence([start, start]),
        timer=_sequence([20.0, 20.25]),
    )
    with pytest.raises(AITimeoutError):
        service.execute(provider="openai", model="configured-model", request=_request())

    with create_session_factory(engine)() as database:
        calls = database.scalars(select(AICall)).all()
        assert len(calls) == 1
        call = calls[0]
        assert call.status == "ERROR"
        assert call.error_code == "TIMEOUT"
        assert call.duration_ms == 250
        assert call.input_tokens == 0
        assert call.estimated_cost is None
