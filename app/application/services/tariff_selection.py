"""M15 semantic tariff selection using metadata only and a structured AI result."""

import json
from decimal import Decimal
from typing import Protocol, cast
from uuid import UUID

from app.application.services.ai import AIExecutionResult
from app.domain.tariffs.selection import (
    TariffSelectionOutput,
    TariffSelectionRecord,
    TariffSelectionStatus,
)
from app.ports.ai import AIInvalidResponseError, AIMessage, AIPrompt, AIRequest, AITask
from app.ports.tariff_selection import TariffSelectionRepository


class SelectionAIExecutor(Protocol):
    def execute(
        self, *, provider: str, model: str, request: AIRequest, audit_run_id: UUID | None = None
    ) -> AIExecutionResult: ...


class SelectionPromptProvider(Protocol):
    def load(self, name: str, version: str) -> AIPrompt: ...


class TariffSelectionService:
    def __init__(
        self,
        *,
        repository: TariffSelectionRepository,
        ai: SelectionAIExecutor,
        prompt_provider: SelectionPromptProvider,
        provider: str,
        model: str,
        min_confidence: Decimal,
    ) -> None:
        self._repository = repository
        self._ai = ai
        self._prompt_provider = prompt_provider
        self._provider = provider
        self._model = model
        self._min_confidence = min_confidence

    def select(self, invoice_id: UUID) -> TariffSelectionRecord:
        with self._repository.selection_guard(invoice_id):
            existing = self._repository.existing(invoice_id)
            if existing is not None:
                return existing
            context = self._repository.context(invoice_id)
            if context is None:
                raise LookupError("invoice not found")
            if not context.candidates:
                return self._repository.save(
                    invoice_id,
                    status=TariffSelectionStatus.NO_TARIFF,
                    selected_tariff_ids=(),
                    confidence=None,
                    threshold=self._min_confidence,
                    reason="No active tariff exists in the catalog.",
                    ai_call_id=None,
                )
            payload = {
                "invoice": {
                    "partner_name": context.partner_name,
                    "invoice_number": context.invoice_number,
                    "issue_date": context.issue_date.isoformat() if context.issue_date else None,
                    "due_date": context.due_date.isoformat() if context.due_date else None,
                    "currency": context.currency,
                    "amount_charged": (
                        str(context.amount_charged) if context.amount_charged is not None else None
                    ),
                    "documents": list(context.documents),
                },
                "active_tariff_catalog": [
                    {
                        "id": str(item.id),
                        "filename": item.original_filename,
                        "extension": item.extension,
                        "description": item.description,
                        "notes": item.notes,
                        "version": item.version,
                        "uploaded_at": item.created_at.isoformat(),
                    }
                    for item in context.candidates
                ],
            }
            executed = self._ai.execute(
                provider=self._provider,
                model=self._model,
                request=AIRequest(
                    task=AITask.TARIFF_SELECTION,
                    prompt=self._prompt_provider.load("tariff_selection", "1"),
                    messages=(AIMessage("user", json.dumps(payload, ensure_ascii=False)),),
                    output_model=TariffSelectionOutput,
                ),
            )
            output = cast(TariffSelectionOutput, executed.result.output)
            candidate_ids = {item.id for item in context.candidates}
            if not set(output.selected_tariff_ids) <= candidate_ids:
                raise AIInvalidResponseError(
                    "tariff selection referenced an inactive or unknown ID"
                )
            if output.confidence < self._min_confidence:
                status = TariffSelectionStatus.LOW_CONFIDENCE
                selected_ids: tuple[UUID, ...] = ()
            elif not output.selected_tariff_ids:
                status = TariffSelectionStatus.NO_TARIFF
                selected_ids = ()
            else:
                status = TariffSelectionStatus.SELECTED
                selected_ids = tuple(output.selected_tariff_ids)
            return self._repository.save(
                invoice_id,
                status=status,
                selected_tariff_ids=selected_ids,
                confidence=output.confidence,
                threshold=self._min_confidence,
                reason=output.reason,
                ai_call_id=executed.call_id,
            )
