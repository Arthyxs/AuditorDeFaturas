"""Strict declarative calculation and financial result models."""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CalculationError(Exception):
    """Safe deterministic calculation failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class Operation(StrEnum):
    SUM = "sum"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    DIVIDE = "divide"
    MAX = "max"
    MIN = "min"
    PERCENT = "percent"
    ROUND = "round"
    CEIL = "ceil"
    FLOOR = "floor"
    COMPARE = "compare"


class Comparator(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


class DecimalLiteral(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    value: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[+-]?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$",
    )

    def decimal(self) -> Decimal:
        value = Decimal(self.value)
        if not value.is_finite():
            raise CalculationError("INVALID_NUMBER", "decimal literal must be finite")
        return value


class CalculationExpression(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Operation
    operands: tuple["CalculationExpression | DecimalLiteral", ...]
    scale: int | None = Field(default=None, ge=0, le=12)
    comparator: Comparator | None = None

    @field_validator("operands")
    @classmethod
    def require_operands(
        cls, value: tuple["CalculationExpression | DecimalLiteral", ...]
    ) -> tuple["CalculationExpression | DecimalLiteral", ...]:
        if not value:
            raise ValueError("calculation expression requires operands")
        return value


class CalculationStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    step: int
    operation: Operation
    inputs: tuple[str | bool, ...]
    result: str | bool
    scale: int | None = None
    comparator: Comparator | None = None


class CalculationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    result: str | bool
    trace: tuple[CalculationStep, ...]


class ToleranceResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    charged_raw: str
    expected_raw: str
    difference_raw: str
    difference_rounded: str
    allowed_difference: str
    within_tolerance: bool


class DocumentAuditStatus(StrEnum):
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    PENDING_MISSING_INFO = "PENDING_MISSING_INFO"
    PENDING_AMBIGUITY = "PENDING_AMBIGUITY"
    PENDING_NO_TARIFF = "PENDING_NO_TARIFF"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    ERROR = "ERROR"


class InvoiceAuditStatus(StrEnum):
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    PENDING = "PENDING"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NOT_AUDITABLE = "NOT_AUDITABLE"
    ERROR = "ERROR"


class ConsolidationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: InvoiceAuditStatus
    counts: dict[DocumentAuditStatus, int]


class MarginResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    revenue: str | None
    actual_cost: str | None
    expected_cost: str | None
    gross_margin_actual: str | None
    gross_margin_expected: str | None
    gross_margin_actual_percent: str | None
    gross_margin_expected_percent: str | None


CalculationExpression.model_rebuild()
