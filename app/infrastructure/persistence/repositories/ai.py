"""PostgreSQL AI pricing and telemetry repository."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select

from app.infrastructure.persistence.models import AICall, AIPriceVersion
from app.infrastructure.persistence.session import SessionFactory
from app.ports.ai import (
    AIPriceVersion as AIPriceRecord,
)
from app.ports.ai import (
    AITelemetryRepository,
    NewAICall,
)


class PostgreSQLAITelemetryRepository(AITelemetryRepository):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add_price(
        self,
        *,
        provider: str,
        model: str,
        version: str,
        effective_from: datetime,
        effective_to: datetime | None,
        input_per_million: Decimal,
        cached_input_per_million: Decimal,
        output_per_million: Decimal,
        currency: str = "USD",
    ) -> AIPriceRecord:
        database = self._session_factory()
        try:
            with database.begin():
                overlap_filters = [
                    AIPriceVersion.provider == provider.casefold(),
                    AIPriceVersion.model == model,
                    or_(
                        AIPriceVersion.effective_to.is_(None),
                        AIPriceVersion.effective_to > effective_from,
                    ),
                ]
                if effective_to is not None:
                    overlap_filters.append(AIPriceVersion.effective_from < effective_to)
                overlap = database.scalar(
                    select(AIPriceVersion.id).where(*overlap_filters).limit(1)
                )
                if overlap is not None:
                    raise ValueError("AI price effective windows must not overlap")
                price = AIPriceVersion(
                    provider=provider.casefold(),
                    model=model,
                    version=version,
                    effective_from=effective_from,
                    effective_to=effective_to,
                    input_per_million=input_per_million,
                    cached_input_per_million=cached_input_per_million,
                    output_per_million=output_per_million,
                    currency=currency.upper(),
                )
                database.add(price)
                database.flush()
                return self._price_record(price)
        finally:
            database.close()

    def effective_price(self, *, provider: str, model: str, at: datetime) -> AIPriceRecord | None:
        database = self._session_factory()
        try:
            price = database.scalar(
                select(AIPriceVersion)
                .where(
                    AIPriceVersion.provider == provider.casefold(),
                    AIPriceVersion.model == model,
                    AIPriceVersion.effective_from <= at,
                    or_(AIPriceVersion.effective_to.is_(None), AIPriceVersion.effective_to > at),
                )
                .order_by(AIPriceVersion.effective_from.desc())
                .limit(1)
            )
            return None if price is None else self._price_record(price)
        finally:
            database.close()

    def record_call(self, call: NewAICall) -> UUID:
        database = self._session_factory()
        try:
            with database.begin():
                model = AICall(
                    provider=call.provider.casefold(),
                    model=call.model,
                    task=call.task.value,
                    provider_request_id=call.provider_request_id,
                    started_at=call.started_at,
                    completed_at=call.completed_at,
                    duration_ms=call.duration_ms,
                    input_tokens=call.input_tokens,
                    cached_input_tokens=call.cached_input_tokens,
                    output_tokens=call.output_tokens,
                    estimated_cost=call.estimated_cost,
                    currency=call.currency,
                    status=call.status,
                    error_code=call.error_code,
                    error_detail=call.error_detail,
                    prompt_name=call.prompt_name,
                    prompt_version=call.prompt_version,
                    prompt_hash=call.prompt_hash,
                    tool_rounds=call.tool_rounds,
                    tool_calls=call.tool_calls,
                    price_version_id=call.price_version_id,
                    audit_run_id=call.audit_run_id,
                )
                database.add(model)
                database.flush()
                return model.id
        finally:
            database.close()

    @staticmethod
    def _price_record(model: AIPriceVersion) -> AIPriceRecord:
        return AIPriceRecord(
            id=model.id,
            provider=model.provider,
            model=model.model,
            version=model.version,
            effective_from=model.effective_from,
            effective_to=model.effective_to,
            input_per_million=model.input_per_million,
            cached_input_per_million=model.cached_input_per_million,
            output_per_million=model.output_per_million,
            currency=model.currency,
        )
