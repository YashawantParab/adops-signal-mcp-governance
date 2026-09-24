from __future__ import annotations

import json
from typing import Any

import anthropic
from anthropic import Anthropic

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

# Anthropic's Messages API requires a positive max_tokens; the agent's
# structured decisions (a tool name plus small JSON arguments) never need a
# large budget, so this is a fixed operational ceiling, not a user setting.
_MAX_OUTPUT_TOKENS = 2048


class AnthropicProvider(LLMProvider):
    provider_name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def model(self) -> str:
        return self._settings.anthropic_model

    @property
    def available(self) -> bool:
        return bool(self._settings.llm_enabled and self._settings.anthropic_api_key)

    def _client(self) -> Anthropic:
        return Anthropic(
            api_key=self._settings.anthropic_api_key,
            timeout=self._settings.anthropic_timeout_seconds,
            max_retries=1,
        )

    @staticmethod
    def _tool_schema(tools: list[ToolSpec]) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema or {"type": "object", "properties": {}},
            }
            for tool in tools
        ]

    @staticmethod
    def _build_messages(initial_query: str, history: list[Turn]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "user", "content": [{"type": "text", "text": initial_query}]}]
        for turn in history:
            if isinstance(turn, UserTurn):
                messages.append({"role": "user", "content": [{"type": "text", "text": turn.content}]})
            elif isinstance(turn, AssistantToolCallTurn):
                call = turn.tool_call
                messages.append(
                    {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}],
                    }
                )
            elif isinstance(turn, ToolResultTurn):
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": turn.tool_call_id,
                                "content": [{"type": "text", "text": _safe_json(turn.content)}],
                            }
                        ],
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
            raise ProviderError("Anthropic provider is not configured (missing ANTHROPIC_API_KEY)")
        try:
            response = self._client().messages.create(
                model=self._settings.anthropic_model,
                max_tokens=_MAX_OUTPUT_TOKENS,
                system=system_prompt,
                messages=self._build_messages(initial_query, history),
                tools=self._tool_schema(tools),
                tool_choice={"type": "any"},
            )
        except anthropic.APIError as exc:
            raise ProviderError(f"Anthropic request failed: {exc}") from exc

        tool_use = next((block for block in response.content if block.type == "tool_use"), None)
        if tool_use is None:
            raise ProviderError("Anthropic response did not include a tool_use block")

        usage = response.usage
        return StepResult(
            tool_call=ToolCall(id=tool_use.id, name=tool_use.name, arguments=dict(tool_use.input or {})),
            usage=StepUsage(
                input_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                total_tokens=(usage.input_tokens + usage.output_tokens) if usage else None,
            ),
            raw_model_name=response.model,
        )

    def classify(
        self, *, system_prompt: str, payload: dict[str, Any], schema: dict[str, Any]
    ) -> ClassificationResult:
        if not self.available:
            raise ProviderError("Anthropic provider is not configured (missing ANTHROPIC_API_KEY)")
        try:
            response = self._client().messages.create(
                model=self._settings.anthropic_model,
                max_tokens=_MAX_OUTPUT_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": [{"type": "text", "text": _safe_json(payload)}]}],
                tools=[{"name": "answer", "description": "Report the classification decision.", "input_schema": schema}],
                tool_choice={"type": "tool", "name": "answer"},
            )
        except anthropic.APIError as exc:
            raise ProviderError(f"Anthropic classification request failed: {exc}") from exc

        tool_use = next((block for block in response.content if block.type == "tool_use"), None)
        if tool_use is None:
            raise ProviderError("Anthropic classification response did not include a tool_use block")
        parsed = dict(tool_use.input or {})
        if "decision" not in parsed:
            raise ProviderError("Anthropic classification response is missing 'decision'")

        usage = response.usage
        return ClassificationResult(
            decision=str(parsed["decision"]),
            confidence=_coerce_confidence(parsed.get("confidence")),
            raw_model_name=response.model,
            usage=StepUsage(
                input_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                total_tokens=(usage.input_tokens + usage.output_tokens) if usage else None,
            ),
        )


def _safe_json(content: dict[str, Any]) -> str:
    return json.dumps(content, default=str)


def _coerce_confidence(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
