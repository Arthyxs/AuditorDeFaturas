"""Provider routing, pricing and immutable telemetry for logical AI calls."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from time import perf_counter
from uuid import UUID

from app.ports.ai import (
    AIInvalidResponseError,
    AIPriceVersion,
    AIProvider,
    AIProviderError,
    AIRequest,
    AIResult,
    AITelemetryRepository,
    NewAICall,
)

_MILLION = Decimal("1000000")
_COST_QUANTUM = Decimal("0.00000001")


@dataclass(frozen=True)
class AIExecutionResult:
    result: AIResult
    call_id: UUID
    estimated_cost: Decimal | None
    currency: str | None


class AIProviderRouter:
    def __init__(self, providers: dict[str, AIProvider]) -> None:
        self._providers = {name.casefold(): provider for name, provider in providers.items()}

    def resolve(self, provider: str) -> AIProvider:
        resolved = self._providers.get(provider.casefold())
        if resolved is None:
            raise LookupError(f"AI provider {provider!r} is not registered")
        return resolved


class AIExecutionService:
    def __init__(
        self,
        *,
        router: AIProviderRouter,
        telemetry: AITelemetryRepository,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        timer: Callable[[], float] = perf_counter,
    ) -> None:
        self._router = router
        self._telemetry = telemetry
        self._now = now
        self._timer = timer

    def execute(
        self,
        *,
        provider: str,
        model: str,
        request: AIRequest,
        audit_run_id: UUID | None = None,
    ) -> AIExecutionResult:
        implementation = self._router.resolve(provider)
        started_at = self._now()
        started_timer = self._timer()
        try:
            result = implementation.generate(model=model, request=request)
            if (
                result.usage.input_tokens < 0
                or result.usage.cached_input_tokens < 0
                or result.usage.output_tokens < 0
                or result.usage.cached_input_tokens > result.usage.input_tokens
            ):
                raise AIInvalidResponseError("AI provider returned invalid token accounting")
        except AIProviderError as exc:
            completed_at = self._now()
            self._telemetry.record_call(
                self._call(
                    provider=provider,
                    model=model,
                    request=request,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=self._duration_ms(started_timer),
                    status="ERROR",
                    error_code=exc.code,
                    error_detail=self._safe_error(exc),
                    audit_run_id=audit_run_id,
                )
            )
            raise

        completed_at = self._now()
        price = self._telemetry.effective_price(provider=provider, model=model, at=started_at)
        cost = self._estimate_cost(result, price)
        call_id = self._telemetry.record_call(
            self._call(
                provider=provider,
                model=model,
                request=request,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=self._duration_ms(started_timer),
                status="SUCCEEDED",
                result=result,
                estimated_cost=cost,
                currency=price.currency if price else None,
                price_version_id=price.id if price else None,
                audit_run_id=audit_run_id,
            )
        )
        return AIExecutionResult(
            result=result,
            call_id=call_id,
            estimated_cost=cost,
            currency=price.currency if price else None,
        )

    def _duration_ms(self, started_timer: float) -> int:
        return max(0, round((self._timer() - started_timer) * 1000))

    @staticmethod
    def _estimate_cost(result: AIResult, price: AIPriceVersion | None) -> Decimal | None:
        if price is None:
            return None
        uncached = result.usage.input_tokens - result.usage.cached_input_tokens
        value = (
            Decimal(uncached) * price.input_per_million
            + Decimal(result.usage.cached_input_tokens) * price.cached_input_per_million
            + Decimal(result.usage.output_tokens) * price.output_per_million
        ) / _MILLION
        return value.quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)

    @staticmethod
    def _safe_error(exc: AIProviderError) -> str:
        value = str(exc).replace("\r", " ").replace("\n", " ")[:1000]
        if any(
            marker in value.casefold()
            for marker in ("password", "secret", "token", "api_key", "apikey", "://")
        ):
            return "sensitive AI error detail redacted"
        return value or exc.code

    @staticmethod
    def _call(
        *,
        provider: str,
        model: str,
        request: AIRequest,
        started_at: datetime,
        completed_at: datetime,
        duration_ms: int,
        status: str,
        result: AIResult | None = None,
        estimated_cost: Decimal | None = None,
        currency: str | None = None,
        price_version_id: UUID | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
        audit_run_id: UUID | None = None,
    ) -> NewAICall:
        return NewAICall(
            provider=provider,
            model=model,
            task=request.task,
            provider_request_id=result.provider_request_id if result else None,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            input_tokens=result.usage.input_tokens if result else 0,
            cached_input_tokens=result.usage.cached_input_tokens if result else 0,
            output_tokens=result.usage.output_tokens if result else 0,
            estimated_cost=estimated_cost,
            currency=currency,
            status=status,
            error_code=error_code,
            error_detail=error_detail,
            prompt_name=request.prompt.name,
            prompt_version=request.prompt.version,
            prompt_hash=request.prompt.sha256,
            tool_rounds=result.tool_rounds if result else 0,
            tool_calls=result.tool_calls if result else 0,
            price_version_id=price_version_id,
            audit_run_id=audit_run_id,
        )
