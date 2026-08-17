"""Deterministic scripted AI provider for application and contract tests."""

from collections import deque

from app.ports.ai import AIProvider, AIProviderError, AIRequest, AIResult


class ScriptedAIProvider(AIProvider):
    def __init__(self, responses: list[AIResult | AIProviderError]) -> None:
        self._responses = deque(responses)
        self.calls: list[tuple[str, AIRequest]] = []

    def generate(self, *, model: str, request: AIRequest) -> AIResult:
        self.calls.append((model, request))
        if not self._responses:
            raise RuntimeError("scripted AI provider has no remaining response")
        response = self._responses.popleft()
        if isinstance(response, AIProviderError):
            raise response
        return response
