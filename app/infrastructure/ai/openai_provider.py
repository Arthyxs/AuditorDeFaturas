"""OpenAI Responses API adapter; the only application module importing the OpenAI SDK."""

from __future__ import annotations

import json
import re
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from app.ports.ai import (
    AIInvalidResponseError,
    AIMissingCredentialError,
    AIProvider,
    AIRateLimitError,
    AIRequest,
    AIRequestRejectedError,
    AIResult,
    AITimeoutError,
    AITool,
    AIToolExecutionError,
    AIToolLoopLimitError,
    AITransportError,
    AIUsage,
)

_TOOL_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


class OpenAIProvider(AIProvider):
    """Run strict JSON Schema Responses calls and a bounded local function-tool loop."""

    def __init__(
        self,
        *,
        api_key: str | None,
        timeout_seconds: float = 120.0,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key.strip() if api_key else ""
        self._timeout_seconds = timeout_seconds
        self._client = client

    def _resolved_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise AIMissingCredentialError
        self._client = OpenAI(
            api_key=self._api_key,
            timeout=self._timeout_seconds,
            max_retries=0,
        )
        return self._client

    def generate(self, *, model: str, request: AIRequest) -> AIResult:
        if not model.strip():
            raise ValueError("AI model must not be empty")
        if request.max_tool_rounds < 0 or request.max_tool_calls < 0:
            raise ValueError("AI tool limits must not be negative")
        tools = self._tool_map(request.tools)
        tool_payloads = [self._tool_payload(tool) for tool in request.tools]
        input_payload: Any = [
            {"role": message.role, "content": message.content} for message in request.messages
        ]
        previous_response_id: str | None = None
        usage = AIUsage(0, 0, 0)
        total_tool_calls = 0
        tool_rounds = 0
        final_request_id: str | None = None

        while True:
            response = self._create_response(
                model=model,
                request=request,
                input_payload=input_payload,
                previous_response_id=previous_response_id,
                tool_payloads=tool_payloads,
            )
            final_request_id = (
                str(getattr(response, "_request_id", None) or getattr(response, "id", "") or "")
                or None
            )
            usage = self._add_usage(usage, response)
            calls = [
                item
                for item in getattr(response, "output", ())
                if getattr(item, "type", None) == "function_call"
            ]
            if not calls:
                if getattr(response, "status", "completed") != "completed":
                    raise AIInvalidResponseError("AI response did not complete")
                return AIResult(
                    output=self._validated_output(response, request.output_model),
                    provider_request_id=final_request_id,
                    usage=usage,
                    tool_rounds=tool_rounds,
                    tool_calls=total_tool_calls,
                )

            tool_rounds += 1
            total_tool_calls += len(calls)
            if tool_rounds > request.max_tool_rounds or total_tool_calls > request.max_tool_calls:
                raise AIToolLoopLimitError
            outputs: list[dict[str, str]] = []
            for call in calls:
                name = str(getattr(call, "name", ""))
                tool = tools.get(name)
                call_id = str(getattr(call, "call_id", ""))
                if tool is None or not call_id:
                    raise AIInvalidResponseError("AI requested an unknown or untraceable tool")
                try:
                    arguments = tool.input_model.model_validate_json(
                        str(getattr(call, "arguments", ""))
                    )
                    tool_output = tool.handler(arguments)
                    serialized = self._serialize_tool_output(tool_output)
                except Exception as exc:
                    raise AIToolExecutionError(name) from exc
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": serialized,
                    }
                )
            previous_response_id = str(getattr(response, "id", "")) or None
            if previous_response_id is None:
                raise AIInvalidResponseError("AI tool response lacks a response identity")
            input_payload = outputs

    def _create_response(
        self,
        *,
        model: str,
        request: AIRequest,
        input_payload: Any,
        previous_response_id: str | None,
        tool_payloads: list[dict[str, Any]],
    ) -> Any:
        parameters: dict[str, Any] = {
            "model": model,
            "instructions": request.prompt.content,
            "input": input_payload,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.output_model.__name__[:64],
                    "schema": request.output_model.model_json_schema(),
                    "strict": True,
                }
            },
            "tools": tool_payloads,
            "parallel_tool_calls": False,
            "store": False,
        }
        if request.max_output_tokens is not None:
            parameters["max_output_tokens"] = request.max_output_tokens
        if previous_response_id is not None:
            parameters["previous_response_id"] = previous_response_id
        try:
            return self._resolved_client().responses.create(**parameters)
        except APITimeoutError as exc:
            raise AITimeoutError from exc
        except RateLimitError as exc:
            raise AIRateLimitError from exc
        except APIConnectionError as exc:
            raise AITransportError from exc
        except APIStatusError as exc:
            if 400 <= exc.status_code < 500:
                raise AIRequestRejectedError from exc
            raise AITransportError from exc

    @staticmethod
    def _tool_map(tools: tuple[AITool, ...]) -> dict[str, AITool]:
        result: dict[str, AITool] = {}
        for tool in tools:
            if _TOOL_NAME.fullmatch(tool.name) is None or tool.name in result:
                raise ValueError("AI tool names must be unique and API-safe")
            result[tool.name] = tool
        return result

    @staticmethod
    def _tool_payload(tool: AITool) -> dict[str, Any]:
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_model.model_json_schema(),
            "strict": True,
        }

    @staticmethod
    def _serialize_tool_output(value: Any) -> str:
        if isinstance(value, BaseModel):
            return value.model_dump_json()
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _validated_output(response: Any, output_model: type[BaseModel]) -> BaseModel:
        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text:
            raise AIInvalidResponseError
        try:
            return output_model.model_validate_json(output_text)
        except ValidationError as exc:
            raise AIInvalidResponseError from exc

    @staticmethod
    def _add_usage(current: AIUsage, response: Any) -> AIUsage:
        usage = getattr(response, "usage", None)
        details = getattr(usage, "input_tokens_details", None)
        return AIUsage(
            input_tokens=current.input_tokens + int(getattr(usage, "input_tokens", 0) or 0),
            cached_input_tokens=current.cached_input_tokens
            + int(getattr(details, "cached_tokens", 0) or 0),
            output_tokens=current.output_tokens + int(getattr(usage, "output_tokens", 0) or 0),
        )
