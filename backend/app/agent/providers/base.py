from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

# Reserved tool name the agent runtime exposes alongside real MCP tools so a
# provider-agnostic loop can represent "the model is done investigating" as
# just another tool call, instead of needing a second, provider-specific
# "plain text response" code path. See ToolSpec docstring below.
FINISH_TOOL_NAME = "submit_diagnosis"


@dataclass(frozen=True)
class ToolSpec:
    """A tool definition offered to the model for one step.

    Real entries mirror the MCP tool registry (name/description/input_schema
    straight from mcp_client.list_tools()). Exactly one synthetic entry named
    FINISH_TOOL_NAME is always included so the model has a uniform way to end
    the investigation with a structured diagnosis, on every provider.
    """

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResultTurn:
    """Feeds a prior tool call's result back into the conversation."""

    tool_call_id: str
    name: str
    content: dict[str, Any]


@dataclass(frozen=True)
class AssistantToolCallTurn:
    """Records a prior step's decision so the model has full history."""

    tool_call: ToolCall


@dataclass(frozen=True)
class UserTurn:
    content: str


Turn = UserTurn | AssistantToolCallTurn | ToolResultTurn


@dataclass(frozen=True)
class StepUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class StepResult:
    """The normalized outcome of one provider round-trip.

    `tool_call.name == FINISH_TOOL_NAME` signals the model is finished; the
    agent runtime is responsible for validating `tool_call.arguments` against
    the diagnosis schema in that case, not this layer.
    """

    tool_call: ToolCall
    usage: StepUsage
    raw_model_name: str


@dataclass(frozen=True)
class ClassificationResult:
    """A single structured classification answer (used by app.gates.llm_gate).

    `schema` passed to `LLMProvider.classify` must describe an object with a
    `decision` property (enum of allowed values) and should include a
    `confidence` property (0-1); this result surfaces whatever the model
    returned for those two fields, defensively (confidence may be None if the
    model omitted it)."""

    decision: str
    confidence: float | None
    raw_model_name: str
    usage: StepUsage


class ProviderError(RuntimeError):
    """Raised for any provider failure (auth, timeout, malformed response, ...).

    The agent runtime catches this at the boundary and degrades to the
    deterministic fallback - no provider SDK exception type should ever
    surface above this layer.
    """


class LLMProvider(ABC):
    """Provider-agnostic interface used by the governed MCP agent runtime.

    No provider SDK object (OpenAI/Anthropic client, response type, etc.)
    may leak past a concrete implementation of this interface - every method
    here takes and returns only the plain dataclasses defined in this module.
    """

    provider_name: Literal["openai", "anthropic"]

    @property
    @abstractmethod
    def model(self) -> str: ...

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether this provider has the configuration it needs (e.g. an API key)."""

    @abstractmethod
    def decide_next_step(
        self,
        *,
        system_prompt: str,
        initial_query: str,
        history: list[Turn],
        tools: list[ToolSpec],
    ) -> StepResult:
        """Ask the model to pick exactly one tool call (real tool, or finish).

        Must raise ProviderError on any failure - auth, timeout, rate limit,
        malformed/unparseable response, or a response that names a tool that
        was not offered. Never raises the underlying SDK's exception type.
        """
        raise NotImplementedError

    @abstractmethod
    def classify(
        self, *, system_prompt: str, payload: dict[str, Any], schema: dict[str, Any]
    ) -> ClassificationResult:
        """A single structured classification call, used by app.gates.llm_gate.

        `schema` is a JSON schema for an object with (at least) `decision` and
        `confidence` properties. Must raise ProviderError on any failure -
        same contract as decide_next_step.
        """
        raise NotImplementedError
