"""Allowlisted Decimal evaluator; arbitrary code and dynamic name lookup are impossible."""

from decimal import (
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_UP,
    Decimal,
    DivisionByZero,
    localcontext,
)

from app.calculation.models import (
    CalculationError,
    CalculationExpression,
    CalculationResult,
    CalculationStep,
    Comparator,
    DecimalLiteral,
    Operation,
)

type _Value = Decimal | bool


class DecimalCalculator:
    def __init__(self, *, max_depth: int = 20, max_nodes: int = 200) -> None:
        if max_depth < 1 or max_nodes < 1:
            raise ValueError("calculator limits must be positive")
        self._max_depth = max_depth
        self._max_nodes = max_nodes

    def calculate(self, expression: CalculationExpression) -> CalculationResult:
        trace: list[CalculationStep] = []
        node_count = [0]
        with localcontext() as context:
            context.prec = 50
            context.rounding = ROUND_HALF_UP
            result = self._evaluate(expression, depth=1, node_count=node_count, trace=trace)
        return CalculationResult(result=self._serialize(result), trace=tuple(trace))

    def _evaluate(
        self,
        expression: CalculationExpression,
        *,
        depth: int,
        node_count: list[int],
        trace: list[CalculationStep],
    ) -> _Value:
        node_count[0] += 1
        if depth > self._max_depth or node_count[0] > self._max_nodes:
            raise CalculationError("CALCULATION_LIMIT", "calculation complexity limit exceeded")
        values: list[_Value] = []
        for operand in expression.operands:
            if isinstance(operand, DecimalLiteral):
                node_count[0] += 1
                if node_count[0] > self._max_nodes:
                    raise CalculationError(
                        "CALCULATION_LIMIT", "calculation complexity limit exceeded"
                    )
                values.append(operand.decimal())
            else:
                values.append(
                    self._evaluate(operand, depth=depth + 1, node_count=node_count, trace=trace)
                )
        result = self._apply(expression, values)
        trace.append(
            CalculationStep(
                step=len(trace) + 1,
                operation=expression.operation,
                inputs=tuple(self._serialize(value) for value in values),
                result=self._serialize(result),
                scale=expression.scale,
                comparator=expression.comparator,
            )
        )
        return result

    def _apply(self, expression: CalculationExpression, values: list[_Value]) -> _Value:
        operation = expression.operation
        if operation is Operation.COMPARE:
            decimals = self._decimals(values, exact=2)
            if expression.comparator is None:
                raise CalculationError("INVALID_EXPRESSION", "compare requires a comparator")
            return self._compare(decimals[0], decimals[1], expression.comparator)
        if expression.comparator is not None:
            raise CalculationError("INVALID_EXPRESSION", "comparator is allowed only for compare")
        decimals = self._decimals(values)
        if operation is Operation.SUM:
            return sum(decimals, Decimal("0"))
        if operation is Operation.SUBTRACT:
            self._arity(decimals, exact=2)
            return decimals[0] - decimals[1]
        if operation is Operation.MULTIPLY:
            self._arity(decimals, minimum=2)
            result = Decimal("1")
            for value in decimals:
                result *= value
            return result
        if operation is Operation.DIVIDE:
            self._arity(decimals, exact=2)
            if decimals[1] == Decimal("0"):
                raise CalculationError("DIVISION_BY_ZERO", "division by zero")
            try:
                return decimals[0] / decimals[1]
            except DivisionByZero as exc:
                raise CalculationError("DIVISION_BY_ZERO", "division by zero") from exc
        if operation is Operation.MAX:
            return max(decimals)
        if operation is Operation.MIN:
            return min(decimals)
        if operation is Operation.PERCENT:
            self._arity(decimals, exact=2)
            return decimals[0] * decimals[1] / Decimal("100")
        if operation in {Operation.ROUND, Operation.CEIL, Operation.FLOOR}:
            self._arity(decimals, exact=1)
            scale = expression.scale if expression.scale is not None else 0
            quantum = Decimal("1").scaleb(-scale)
            rounding = {
                Operation.ROUND: ROUND_HALF_UP,
                Operation.CEIL: ROUND_CEILING,
                Operation.FLOOR: ROUND_FLOOR,
            }[operation]
            return decimals[0].quantize(quantum, rounding=rounding)
        raise CalculationError("OPERATION_NOT_ALLOWED", "calculation operation is not allowlisted")

    @staticmethod
    def _serialize(value: _Value) -> str | bool:
        return value if isinstance(value, bool) else format(value, "f")

    @staticmethod
    def _decimals(values: list[_Value], *, exact: int | None = None) -> list[Decimal]:
        if any(isinstance(value, bool) for value in values):
            raise CalculationError("INVALID_EXPRESSION", "boolean cannot be used as money")
        decimals = [value for value in values if isinstance(value, Decimal)]
        DecimalCalculator._arity(decimals, exact=exact, minimum=1 if exact is None else None)
        return decimals

    @staticmethod
    def _arity(
        values: list[Decimal], *, exact: int | None = None, minimum: int | None = None
    ) -> None:
        if exact is not None and len(values) != exact:
            raise CalculationError("INVALID_EXPRESSION", f"operation requires {exact} operands")
        if minimum is not None and len(values) < minimum:
            raise CalculationError(
                "INVALID_EXPRESSION", f"operation requires at least {minimum} operands"
            )

    @staticmethod
    def _compare(left: Decimal, right: Decimal, comparator: Comparator) -> bool:
        return {
            Comparator.EQ: left == right,
            Comparator.NE: left != right,
            Comparator.GT: left > right,
            Comparator.GTE: left >= right,
            Comparator.LT: left < right,
            Comparator.LTE: left <= right,
        }[comparator]
