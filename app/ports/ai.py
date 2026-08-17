"""Replaceable AI execution, structured-output and telemetry contracts."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel


class AITask(StrEnum):
    EMAIL_CLASSIFICATION = "EMAIL_CLASSIFICATION"
    TARIFF_SELECTION = "TARIFF_SELECTION"
    INVOICE_AUDIT = "INVOICE_AUDIT"
    REANALYSIS = "REANALYSIS"
    PROVIDER_CONTRACT = "PROVIDER_CONTRACT"


class AIProviderError(Exception):
    """Provider-neutral failure with a stable, non-secret telemetry code."""

    def __init__(self, message: str, *, code: str, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class AIMissingCredentialError(AIProviderError):
    def __init__(self) -> None:
        super().__init__(
            "AI provider credential is not configured", code="MISSING_CREDENTIAL", retryable=False
        )


class AITimeoutError(AIProviderError):
    def __init__(self) -> None:
        super().__init__("AI provider timed out", code="TIMEOUT", retryable=True)


class AIRateLimitError(AIProviderError):
    def __init__(self) -> None:
        super().__init__("AI provider rate limit reached", code="RATE_LIMIT", retryable=True)


class AITransportError(AIProviderError):
    def __init__(self) -> None:
        super().__init__("AI provider transport failed", code="TRANSPORT_ERROR", retryable=True)


class AIRequestRejectedError(AIProviderError):
    def __init__(self) -> None:
        super().__init__(
            "AI provider rejected the request", code="REQUEST_REJECTED", retryable=False
        )


class AIInvalidResponseError(AIProviderError):
    def __init__(
        self, message: str = "AI provider returned an invalid structured response"
    ) -> None:
        super().__init__(message, code="INVALID_RESPONSE", retryable=False)


class AIToolLoopLimitError(AIProviderError):
    def __init__(self) -> None:
        super().__init__(
            "AI tool loop exceeded configured limits", code="TOOL_LIMIT", retryable=False
        )


class AIToolExecutionError(AIProviderError):
    def __init__(self, tool_name: str) -> None:
        super().__init__(
            f"AI tool execution failed for {tool_name!r}",
            code="TOOL_ERROR",
            retryable=False,
        )


@dataclass(frozen=True)
class AIPrompt:
    name: str
    version: str
    sha256: str
    content: str


@dataclass(frozen=True)
class AIMessage:
    role: str
    content: str


@dataclass(frozen=True)
class AITool:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[BaseModel], Any]


@dataclass(frozen=True)
class AIRequest:
    task: AITask
    prompt: AIPrompt
    messages: tuple[AIMessage, ...]
    output_model: type[BaseModel]
    tools: tuple[AITool, ...] = ()
    max_output_tokens: int | None = None
    max_tool_rounds: int = 5
    max_tool_calls: int = 20


@dataclass(frozen=True)
class AIUsage:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class AIResult:
    output: BaseModel
    provider_request_id: str | None
    usage: AIUsage
    tool_rounds: int
    tool_calls: int


class AIProvider(Protocol):
    """One structured generation capability independent of a vendor SDK."""

    def generate(self, *, model: str, request: AIRequest) -> AIResult:
        """Return schema-validated output or a provider-neutral explicit error."""


@dataclass(frozen=True)
class AIPriceVersion:
    id: UUID
    provider: str
    model: str
    version: str
    effective_from: datetime
    effective_to: datetime | None
    input_per_million: Decimal
    cached_input_per_million: Decimal
    output_per_million: Decimal
    currency: str


@dataclass(frozen=True)
class NewAICall:
    provider: str
    model: str
    task: AITask
    provider_request_id: str | None
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    estimated_cost: Decimal | None
    currency: str | None
    status: str
    error_code: str | None
    error_detail: str | None
    prompt_name: str
    prompt_version: str
    prompt_hash: str
    tool_rounds: int
    tool_calls: int
    price_version_id: UUID | None
    audit_run_id: UUID | None = None


class AITelemetryRepository(Protocol):
    def effective_price(
        self, *, provider: str, model: str, at: datetime
    ) -> AIPriceVersion | None: ...

    def record_call(self, call: NewAICall) -> UUID: ...
