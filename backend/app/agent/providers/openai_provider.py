from __future__ import annotations

import json
from typing import Any

from openai import OpenAI, OpenAIError

from app.agent.providers.base import (
    AssistantToolCallTurn,
    ClassificationResult,
    LLMProvider,
    ProviderError,
    StepResult,
    StepUsage,
    ToolCall,
    ToolResultTurn,
    ToolSpec,
    Turn,
    UserTurn,
)
from app.config import Settings


class OpenAIProvider(LLMProvider):
    provider_name = "openai"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def model(self) -> str:
        return self._settings.openai_model

    @property
    def available(self) -> bool:
        return bool(self._settings.llm_enabled and self._settings.openai_api_key)

    def _client(self) -> OpenAI:
        return OpenAI(
            api_key=self._settings.openai_api_key,
            timeout=self._settings.openai_timeout_seconds,
            max_retries=1,
        )

    @staticmethod
    def _tool_schema(tools: list[ToolSpec]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema or {"type": "object", "properties": {}},
                },
            }
            for tool in tools
        ]

    @staticmethod
    def _build_messages(system_prompt: str, initial_query: str, history: list[Turn]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": initial_query},
        ]
        for turn in history:
            if isinstance(turn, UserTurn):
                messages.append({"role": "user", "content": turn.content})
            elif isinstance(turn, AssistantToolCallTurn):
                call = turn.tool_call
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {"name": call.name, "arguments": json.dumps(call.arguments, default=str)},
                            }
                        ],
                    }
                )
            elif isinstance(turn, ToolResultTurn):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": turn.tool_call_id,
                        "content": json.dumps(turn.content, default=str),
                    }
                )
        return messages

    def decide_next_step(
        self,
        *,
        system_prompt: str,
        initial_query: str,
        history: list[Turn],
        tools: list[ToolSpec],
    ) -> StepResult:
        if not self.available:
            raise ProviderError("OpenAI provider is not configured (missing OPENAI_API_KEY)")
        try:
            response = self._client().chat.completions.create(
                model=self._settings.openai_model,
                messages=self._build_messages(system_prompt, initial_query, history),
                tools=self._tool_schema(tools),
                tool_choice="required",
            )
        except OpenAIError as exc:
            raise ProviderError(f"OpenAI request failed: {exc}") from exc

        choice = response.choices[0] if response.choices else None
        tool_calls = choice.message.tool_calls if choice and choice.message else None
        if not tool_calls:
            raise ProviderError("OpenAI response did not include a tool call")

        call = tool_calls[0]
        try:
            arguments = json.loads(call.function.arguments) if call.function.arguments else {}
        except (json.JSONDecodeError, TypeError) as exc:
            raise ProviderError(f"OpenAI tool call arguments were not valid JSON: {exc}") from exc

        usage = response.usage
        return StepResult(
            tool_call=ToolCall(id=call.id, name=call.function.name, arguments=arguments),
            usage=StepUsage(
                input_tokens=usage.prompt_tokens if usage else None,
                output_tokens=usage.completion_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
            ),
            raw_model_name=response.model,
        )

    def classify(
        self, *, system_prompt: str, payload: dict[str, Any], schema: dict[str, Any]
    ) -> ClassificationResult:
        if not self.available:
            raise ProviderError("OpenAI provider is not configured (missing OPENAI_API_KEY)")
        try:
            response = self._client().chat.completions.create(
                model=self._settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload, default=str)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "gate_decision", "strict": True, "schema": schema},
                },
            )
        except OpenAIError as exc:
            raise ProviderError(f"OpenAI classification request failed: {exc}") from exc

        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise ProviderError("OpenAI classification response was empty")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"OpenAI classification response was not valid JSON: {exc}") from exc
        if "decision" not in parsed:
            raise ProviderError("OpenAI classification response is missing 'decision'")

        usage = response.usage
        return ClassificationResult(
            decision=str(parsed["decision"]),
            confidence=_coerce_confidence(parsed.get("confidence")),
            raw_model_name=response.model,
            usage=StepUsage(
                input_tokens=usage.prompt_tokens if usage else None,
                output_tokens=usage.completion_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
            ),
        )


def _coerce_confidence(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
