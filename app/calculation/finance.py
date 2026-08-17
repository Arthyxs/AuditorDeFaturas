"""Deterministic tolerance, status consolidation and gross-margin rules."""

from collections import Counter
from decimal import ROUND_HALF_UP, Decimal

from app.calculation.models import (
    ConsolidationResult,
    DocumentAuditStatus,
    InvoiceAuditStatus,
    MarginResult,
    ToleranceResult,
)

_MONEY_QUANTUM = Decimal("0.01")
_PERCENT_QUANTUM = Decimal("0.0001")
_PENDING = {
    DocumentAuditStatus.PENDING_MISSING_INFO,
    DocumentAuditStatus.PENDING_AMBIGUITY,
    DocumentAuditStatus.PENDING_NO_TARIFF,
}


def evaluate_tolerance(
    *,
    charged: Decimal,
    expected: Decimal,
    absolute_tolerance: Decimal,
    percent_tolerance: Decimal,
) -> ToleranceResult:
    if absolute_tolerance < 0 or percent_tolerance < 0:
        raise ValueError("tolerances cannot be negative")
    difference = charged - expected
    percentage_allowance = abs(expected) * percent_tolerance / Decimal("100")
    allowed = max(absolute_tolerance, percentage_allowance)
    return ToleranceResult(
        charged_raw=format(charged, "f"),
        expected_raw=format(expected, "f"),
        difference_raw=format(difference, "f"),
        difference_rounded=format(difference.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP), "f"),
        allowed_difference=format(allowed, "f"),
        within_tolerance=abs(difference) <= allowed,
    )


def consolidate_statuses(
    statuses: tuple[DocumentAuditStatus, ...],
) -> ConsolidationResult:
    counts = Counter(statuses)
    if not statuses:
        result = InvoiceAuditStatus.NOT_AUDITABLE
    elif counts[DocumentAuditStatus.INCORRECT]:
        result = InvoiceAuditStatus.INCORRECT
    elif any(counts[item] for item in _PENDING):
        result = InvoiceAuditStatus.PENDING
    elif counts[DocumentAuditStatus.ERROR]:
        result = InvoiceAuditStatus.ERROR
    elif counts[DocumentAuditStatus.MANUAL_REVIEW]:
        result = InvoiceAuditStatus.MANUAL_REVIEW
    elif counts[DocumentAuditStatus.CORRECT] == len(statuses):
        result = InvoiceAuditStatus.CORRECT
    else:
        result = InvoiceAuditStatus.MANUAL_REVIEW
    return ConsolidationResult(status=result, counts=dict(counts))


def gross_margin(
    *, revenue: Decimal | None, actual_cost: Decimal | None, expected_cost: Decimal | None
) -> MarginResult:
    if revenue is None:
        return MarginResult(
            revenue=None,
            actual_cost=_optional(actual_cost),
            expected_cost=_optional(expected_cost),
            gross_margin_actual=None,
            gross_margin_expected=None,
            gross_margin_actual_percent=None,
            gross_margin_expected_percent=None,
        )
    actual = revenue - actual_cost if actual_cost is not None else None
    expected = revenue - expected_cost if expected_cost is not None else None
    return MarginResult(
        revenue=format(revenue, "f"),
        actual_cost=_optional(actual_cost),
        expected_cost=_optional(expected_cost),
        gross_margin_actual=_optional(actual),
        gross_margin_expected=_optional(expected),
        gross_margin_actual_percent=_margin_percent(actual, revenue),
        gross_margin_expected_percent=_margin_percent(expected, revenue),
    )


def _optional(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _margin_percent(margin: Decimal | None, revenue: Decimal) -> str | None:
    if margin is None or revenue == Decimal("0"):
        return None
    return format(
        (margin / revenue * Decimal("100")).quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP),
        "f",
    )
