"""Typed AI tool boundary for the deterministic calculator."""

from pydantic import BaseModel

from app.calculation.calculator import DecimalCalculator
from app.calculation.models import CalculationExpression
from app.ports.ai import AITool


class CalculateInput(BaseModel):
    expression: CalculationExpression


class CalculationAITool:
    def __init__(self, calculator: DecimalCalculator) -> None:
        self._calculator = calculator

    def definition(self) -> AITool:
        return AITool(
            name="calculate_decimal",
            description="Evaluate an allowlisted Decimal expression and return a trace.",
            input_model=CalculateInput,
            handler=self.calculate,
        )

    def calculate(self, value: BaseModel) -> dict[str, object]:
        request = CalculateInput.model_validate(value)
        return self._calculator.calculate(request.expression).model_dump(mode="json")
