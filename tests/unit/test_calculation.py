import ast
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.calculation import (
    CalculationError,
    CalculationExpression,
    DecimalCalculator,
    consolidate_statuses,
    evaluate_tolerance,
    gross_margin,
)
from app.calculation.models import DocumentAuditStatus, InvoiceAuditStatus


def expression(payload: dict[str, object]) -> CalculationExpression:
    return CalculationExpression.model_validate(payload)


def literal(value: str) -> dict[str, str]:
    return {"value": value}


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"operation": "sum", "operands": [literal("0.1"), literal("0.2")]}, "0.3"),
        ({"operation": "subtract", "operands": [literal("10"), literal("3.2")]}, "6.8"),
        ({"operation": "multiply", "operands": [literal("2.5"), literal("4")]}, "10.0"),
        ({"operation": "divide", "operands": [literal("1"), literal("4")]}, "0.25"),
        ({"operation": "max", "operands": [literal("2"), literal("7")]}, "7"),
        ({"operation": "min", "operands": [literal("2"), literal("7")]}, "2"),
        ({"operation": "percent", "operands": [literal("1892.34"), literal("0.30")]}, "5.67702"),
        ({"operation": "round", "operands": [literal("2.345")], "scale": 2}, "2.35"),
        ({"operation": "ceil", "operands": [literal("2.341")], "scale": 2}, "2.35"),
        ({"operation": "floor", "operands": [literal("2.349")], "scale": 2}, "2.34"),
        (
            {
                "operation": "compare",
                "operands": [literal("2.00"), literal("1.99")],
                "comparator": "gt",
            },
            True,
        ),
    ],
)
def test_allowlisted_decimal_operations(payload: dict[str, object], expected: str | bool) -> None:
    result = DecimalCalculator().calculate(expression(payload))
    assert result.result == expected
    assert result.trace[-1].result == expected


def test_nested_expression_has_deterministic_postorder_trace() -> None:
    payload = expression(
        {
            "operation": "round",
            "scale": 2,
            "operands": [
                {
                    "operation": "sum",
                    "operands": [
                        literal("100"),
                        {
                            "operation": "percent",
                            "operands": [literal("100"), literal("0.3")],
                        },
                    ],
                }
            ],
        }
    )
    first = DecimalCalculator().calculate(payload)
    second = DecimalCalculator().calculate(payload)
    assert first == second
    assert [step.operation.value for step in first.trace] == ["percent", "sum", "round"]
    assert first.result == "100.30"


def test_invalid_dsl_float_unknown_operation_and_arbitrary_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        expression({"operation": "sum", "operands": [{"value": 0.1}]})
    with pytest.raises(ValidationError):
        expression({"operation": "eval", "operands": [literal("1")]})
    with pytest.raises(ValidationError):
        expression({"operation": "sum", "operands": [literal("1")], "call": "__import__"})


def test_division_by_zero_boolean_reuse_and_limits_fail_explicitly() -> None:
    with pytest.raises(CalculationError) as zero:
        DecimalCalculator().calculate(
            expression({"operation": "divide", "operands": [literal("1"), literal("0")]})
        )
    assert zero.value.code == "DIVISION_BY_ZERO"

    comparison = {
        "operation": "compare",
        "comparator": "eq",
        "operands": [literal("1"), literal("1")],
    }
    with pytest.raises(CalculationError) as boolean:
        DecimalCalculator().calculate(
            expression({"operation": "sum", "operands": [comparison, literal("1")]})
        )
    assert boolean.value.code == "INVALID_EXPRESSION"

    nested: dict[str, object] = {"operation": "round", "operands": [literal("1")]}
    nested = {"operation": "round", "operands": [nested]}
    with pytest.raises(CalculationError) as limited:
        DecimalCalculator(max_depth=1).calculate(expression(nested))
    assert limited.value.code == "CALCULATION_LIMIT"


def test_tolerance_uses_maximum_of_absolute_and_percentage_and_keeps_raw_values() -> None:
    result = evaluate_tolerance(
        charged=Decimal("100.006"),
        expected=Decimal("100.000"),
        absolute_tolerance=Decimal("0.01"),
        percent_tolerance=Decimal("0.02"),
    )
    assert result.difference_raw == "0.006"
    assert result.difference_rounded == "0.01"
    assert result.allowed_difference == "0.02000"
    assert result.within_tolerance


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ((), InvoiceAuditStatus.NOT_AUDITABLE),
        ((DocumentAuditStatus.CORRECT,), InvoiceAuditStatus.CORRECT),
        (
            (DocumentAuditStatus.CORRECT, DocumentAuditStatus.PENDING_AMBIGUITY),
            InvoiceAuditStatus.PENDING,
        ),
        (
            (DocumentAuditStatus.PENDING_MISSING_INFO, DocumentAuditStatus.INCORRECT),
            InvoiceAuditStatus.INCORRECT,
        ),
        ((DocumentAuditStatus.ERROR,), InvoiceAuditStatus.ERROR),
        ((DocumentAuditStatus.MANUAL_REVIEW,), InvoiceAuditStatus.MANUAL_REVIEW),
    ],
)
def test_consolidation_never_hides_pending_or_incorrect(
    statuses: tuple[DocumentAuditStatus, ...], expected: InvoiceAuditStatus
) -> None:
    assert consolidate_statuses(statuses).status is expected


def test_margin_handles_values_zero_revenue_and_missing_revenue() -> None:
    calculated = gross_margin(
        revenue=Decimal("200"), actual_cost=Decimal("150"), expected_cost=Decimal("140")
    )
    assert calculated.gross_margin_actual == "50"
    assert calculated.gross_margin_expected_percent == "30.0000"

    zero = gross_margin(revenue=Decimal("0"), actual_cost=Decimal("10"), expected_cost=None)
    assert zero.gross_margin_actual == "-10"
    assert zero.gross_margin_actual_percent is None

    missing = gross_margin(revenue=None, actual_cost=Decimal("10"), expected_cost=Decimal("9"))
    assert missing.gross_margin_actual is None
    assert missing.gross_margin_expected is None


def test_calculation_package_never_calls_eval_or_exec() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "calculation"
    forbidden = []
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"eval", "exec"}
            ):
                forbidden.append(f"{path.name}:{node.lineno}")
    assert forbidden == []
