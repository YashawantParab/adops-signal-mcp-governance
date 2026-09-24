from __future__ import annotations

from app.agent.providers.anthropic_provider import AnthropicProvider
from app.agent.providers.base import (
    FINISH_TOOL_NAME,
    AssistantToolCallTurn,
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
from app.agent.providers.openai_provider import OpenAIProvider
from app.config import Settings, get_settings

__all__ = [
    "FINISH_TOOL_NAME",
    "AssistantToolCallTurn",
    "LLMProvider",
    "ProviderError",
    "StepResult",
    "StepUsage",
    "ToolCall",
    "ToolResultTurn",
    "ToolSpec",
    "Turn",
    "UserTurn",
    "AnthropicProvider",
    "OpenAIProvider",
    "get_llm_provider",
]


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Env-selected provider factory. Never raises - callers check `.available`."""
    settings = settings or get_settings()
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings)
    return OpenAIProvider(settings)
