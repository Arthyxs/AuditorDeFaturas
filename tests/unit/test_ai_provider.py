"""M12 OpenAI Responses adapter, structured outputs and controlled tools."""

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

import httpx2
import pytest
from openai import APITimeoutError, RateLimitError
from pydantic import BaseModel, ConfigDict

from app.infrastructure.ai.openai_provider import OpenAIProvider
from app.infrastructure.ai.prompts import PromptRepository
from app.ports.ai import (
    AIInvalidResponseError,
    AIMessage,
    AIMissingCredentialError,
    AIPrompt,
    AIRateLimitError,
    AIRequest,
    AITask,
    AITimeoutError,
    AITool,
    AIToolLoopLimitError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ContractOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]
    total: int


class SumInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: int
    right: int


class FakeResponses:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def create(self, **parameters: Any) -> Any:
        self.calls.append(parameters)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = FakeResponses(responses)


def _usage(input_tokens: int, cached: int, output_tokens: int) -> Any:
    return SimpleNamespace(
        input_tokens=input_tokens,
        input_tokens_details=SimpleNamespace(cached_tokens=cached),
        output_tokens=output_tokens,
    )


def _request(*, tools: tuple[AITool, ...] = (), max_tool_rounds: int = 5) -> AIRequest:
    return AIRequest(
        task=AITask.PROVIDER_CONTRACT,
        prompt=AIPrompt("provider_contract", "1", "a" * 64, "Return JSON."),
        messages=(AIMessage("user", "Run the provider contract."),),
        output_model=ContractOutput,
        tools=tools,
        max_output_tokens=200,
        max_tool_rounds=max_tool_rounds,
        max_tool_calls=3,
    )


def test_responses_structured_output_and_bounded_tool_loop() -> None:
    tool_call = SimpleNamespace(
        type="function_call",
        name="sum_values",
        call_id="call-1",
        arguments='{"left":2,"right":3}',
    )
    client = FakeClient(
        [
            SimpleNamespace(
                id="resp-1",
                status="completed",
                output=[tool_call],
                output_text="",
                usage=_usage(10, 2, 3),
            ),
            SimpleNamespace(
                id="resp-2",
                _request_id="request-2",
                status="completed",
                output=[],
                output_text='{"status":"ok","total":5}',
                usage=_usage(4, 1, 5),
            ),
        ]
    )

    def sum_values(value: BaseModel) -> dict[str, int]:
        assert isinstance(value, SumInput)
        return {"total": value.left + value.right}

    tool = AITool(
        name="sum_values",
        description="Add two integers deterministically.",
        input_model=SumInput,
        handler=sum_values,
    )
    result = OpenAIProvider(api_key=None, client=client).generate(
        model="configured-test-model",
        request=_request(tools=(tool,)),
    )

    assert result.output == ContractOutput(status="ok", total=5)
    assert result.provider_request_id == "request-2"
    assert result.usage.input_tokens == 14
    assert result.usage.cached_input_tokens == 3
    assert result.usage.output_tokens == 8
    assert result.tool_rounds == 1
    assert result.tool_calls == 1
    assert len(client.responses.calls) == 2
    first, second = client.responses.calls
    assert first["model"] == "configured-test-model"
    assert first["store"] is False
    assert first["parallel_tool_calls"] is False
    assert first["text"]["format"]["type"] == "json_schema"
    assert first["text"]["format"]["strict"] is True
    assert first["tools"][0]["strict"] is True
    assert second["previous_response_id"] == "resp-1"
    assert second["input"] == [
        {"type": "function_call_output", "call_id": "call-1", "output": '{"total":5}'}
    ]


def test_invalid_schema_output_and_tool_loop_limit_fail_explicitly() -> None:
    invalid_client = FakeClient(
        [
            SimpleNamespace(
                id="invalid",
                status="completed",
                output=[],
                output_text='{"status":"not-ok"}',
                usage=_usage(1, 0, 1),
            )
        ]
    )
    with pytest.raises(AIInvalidResponseError):
        OpenAIProvider(api_key=None, client=invalid_client).generate(
            model="test", request=_request()
        )

    call = SimpleNamespace(
        type="function_call",
        name="sum_values",
        call_id="call-limit",
        arguments='{"left":1,"right":1}',
    )
    limit_client = FakeClient(
        [SimpleNamespace(id="limit", output=[call], output_text="", usage=_usage(1, 0, 1))]
    )
    tool = AITool("sum_values", "sum", SumInput, lambda _: {"total": 2})
    with pytest.raises(AIToolLoopLimitError):
        OpenAIProvider(api_key=None, client=limit_client).generate(
            model="test", request=_request(tools=(tool,), max_tool_rounds=0)
        )


def test_missing_key_timeout_and_rate_limit_are_provider_neutral() -> None:
    with pytest.raises(AIMissingCredentialError):
        OpenAIProvider(api_key=None).generate(model="test", request=_request())

    request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    timeout_client = FakeClient([APITimeoutError(request=request)])
    with pytest.raises(AITimeoutError):
        OpenAIProvider(api_key=None, client=timeout_client).generate(
            model="test", request=_request()
        )

    response = httpx2.Response(429, request=request)
    rate_client = FakeClient([RateLimitError("rate limited", response=response, body=None)])
    with pytest.raises(AIRateLimitError):
        OpenAIProvider(api_key=None, client=rate_client).generate(model="test", request=_request())


def test_versioned_prompt_hash_and_openai_sdk_isolation() -> None:
    prompts = PromptRepository(PROJECT_ROOT / "app" / "infrastructure" / "ai" / "prompts")
    loaded = prompts.load("provider_contract", "1")
    assert loaded.name == "provider_contract"
    assert loaded.version == "1"
    assert len(loaded.sha256) == 64
    with pytest.raises((ValueError, FileNotFoundError)):
        prompts.load("../escape", "1")

    offenders: list[str] = []
    adapter = PROJECT_ROOT / "app" / "infrastructure" / "ai" / "openai_provider.py"
    for path in (PROJECT_ROOT / "app").rglob("*.py"):
        if path == adapter:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(name.name == "openai" for name in node.names):
                offenders.append(str(path))
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("openai")
            ):
                offenders.append(str(path))
    assert offenders == []
