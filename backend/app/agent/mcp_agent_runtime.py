"""The governed MCP agent's bounded step loop.

    campaign/query
      -> construct allowed tool definitions (real MCP tools + one synthetic
         "finish" tool, see providers.base.FINISH_TOOL_NAME)
      -> LLM chooses a tool OR finish
      -> governance wrapper (app.services.governance_wrapper)
      -> MCP tool
      -> evidence (assigned an ID, fed back to the model)
      -> next LLM step
      -> repeat until the model finishes, or a bound is hit
      -> structured final diagnosis, evidence-validated

Every exit that is not a clean "the model finished" is a typed AgentTerminated
with a reason_code the dispatcher (mcp_governance_service.py) turns directly
into the persisted fallback_reason - never a silent, unexplained fallback.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.agent.mcp_client import MCPAgentClient, MCPClientError
from app.agent.providers.base import (
    FINISH_TOOL_NAME,
    AssistantToolCallTurn,
    LLMProvider,
    ProviderError,
    StepUsage,
    ToolCall,
    ToolResultTurn,
    ToolSpec,
    Turn,
)
from app.config import Settings
from app.services.governance_wrapper import GovernedToolOutcome, governed_tool_call

Impact = Literal["High", "Medium", "Low"]


class GovernedCause(BaseModel):
    cause: str = Field(min_length=3, max_length=120)
    impact: Impact
    evidence_ids: list[str] = Field(min_length=1, max_length=4)
    recommendation_title: str = Field(min_length=3, max_length=160)
    recommendation_description: str = Field(min_length=8, max_length=500)
    expected_impact: Impact
    risk_level: Impact


class GovernedDiagnosis(BaseModel):
    diagnosis: str = Field(min_length=20, max_length=1200)
    root_causes: list[GovernedCause] = Field(min_length=1, max_length=4)
    confidence_score: float = Field(ge=0, le=1)
    human_approval_required: bool


SYSTEM_PROMPT = """
You are the SignalOps AI governed MCP agent, investigating one CTV/programmatic AdOps campaign.

You do not have direct database access. You may only see campaign facts by calling the MCP tools
offered to you, one at a time. Every tool result you receive was validated and logged by a
governance layer before reaching you, and is tagged with an evidence_id.

Rules:
1. Call only the tools you are offered, for the exact campaign you were asked to investigate.
2. Gather only the evidence you actually need to answer the operator's question - do not call
   every tool reflexively.
3. When you have enough evidence, call the finish tool ({finish_tool}) exactly once with your
   final structured diagnosis.
4. Every root cause you report must cite one or more evidence_id values that were actually
   returned to you by a tool call in this conversation. Never invent an evidence_id.
5. Never claim a recommendation has been executed - you only diagnose and recommend.
6. Mark human_approval_required true for any change to targeting, bids, frequency, inventory,
   flight dates, or creatives.
7. Do not attribute fault to a specific publisher, advertiser, or partner unless the evidence
   directly supports it.
""".strip().format(finish_tool=FINISH_TOOL_NAME)


class AgentTerminated(RuntimeError):
    """Raised for every non-clean exit from the loop.

    reason_code is one of: max_steps_exceeded, max_tool_calls_exceeded,
    max_tokens_exceeded, timeout, provider_error, mcp_unavailable,
    structured_output_failure, no_evidence_grounded_causes.
    """

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class EvidenceEntry:
    id: str
    tool_name: str
    campaign_id: int
    data: dict[str, Any]


@dataclass
class AgentRunOutcome:
    diagnosis: GovernedDiagnosis
    grounded_root_causes: list[GovernedCause]
    evidence_ledger: dict[str, EvidenceEntry]
    tool_outcomes: list[GovernedToolOutcome]
    tools_selected: list[str]
    steps_used: int
    provider_name: str
    model_name: str
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int


def _finish_tool_spec() -> ToolSpec:
    return ToolSpec(
        name=FINISH_TOOL_NAME,
        description="Call this exactly once, when you have enough evidence, with your final structured diagnosis.",
        input_schema=GovernedDiagnosis.model_json_schema(),
    )


async def run_governed_mcp_agent(
    db: Session,
    *,
    agent_run_id: int,
    campaign_id: int,
    user_query: str,
    provider: LLMProvider,
    settings: Settings,
) -> AgentRunOutcome:
    if not provider.available:
        raise AgentTerminated("missing_provider_key", f"{provider.provider_name} provider has no API key configured")

    try:
        return await asyncio.wait_for(
            _run_loop(db, agent_run_id=agent_run_id, campaign_id=campaign_id, user_query=user_query, provider=provider, settings=settings),
            timeout=settings.agent_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise AgentTerminated("timeout", f"Agent run exceeded {settings.agent_timeout_seconds}s") from exc


async def _run_loop(
    db: Session,
    *,
    agent_run_id: int,
    campaign_id: int,
    user_query: str,
    provider: LLMProvider,
    settings: Settings,
) -> AgentRunOutcome:
    try:
        async with MCPAgentClient(settings=settings) as mcp_client:
            mcp_tools = await mcp_client.list_tools()
            tools = [ToolSpec(name=t.name, description=t.description, input_schema=t.input_schema) for t in mcp_tools]
            tools.append(_finish_tool_spec())

            history: list[Turn] = []
            evidence_ledger: dict[str, EvidenceEntry] = {}
            tool_outcomes: list[GovernedToolOutcome] = []
            tools_selected: list[str] = []
            tool_call_count = 0
            total_input_tokens = 0
            total_output_tokens = 0
            next_evidence_number = 1

            for step in range(1, settings.max_agent_steps + 1):
                try:
                    step_result = provider.decide_next_step(
                        system_prompt=SYSTEM_PROMPT,
                        initial_query=f"Investigate campaign {campaign_id}. Operator question: {user_query}",
                        history=history,
                        tools=tools,
                    )
                except ProviderError as exc:
                    raise AgentTerminated("provider_error", str(exc)) from exc

                total_input_tokens += step_result.usage.input_tokens or 0
                total_output_tokens += step_result.usage.output_tokens or 0
                if settings.max_agent_tokens and (total_input_tokens + total_output_tokens) > settings.max_agent_tokens:
                    raise AgentTerminated(
                        "max_tokens_exceeded",
                        f"Token budget {settings.max_agent_tokens} exceeded after step {step}",
                    )

                call = step_result.tool_call
                history.append(AssistantToolCallTurn(tool_call=call))

                if call.name == FINISH_TOOL_NAME:
                    diagnosis = _validate_diagnosis(call.arguments)
                    grounded = _grounded_causes(diagnosis, evidence_ledger, campaign_id)
                    if not grounded:
                        raise AgentTerminated(
                            "no_evidence_grounded_causes",
                            "Every root cause cited an evidence_id that does not exist in this run's evidence ledger",
                        )
                    return AgentRunOutcome(
                        diagnosis=diagnosis,
                        grounded_root_causes=grounded,
                        evidence_ledger=evidence_ledger,
                        tool_outcomes=tool_outcomes,
                        tools_selected=tools_selected,
                        steps_used=step,
                        provider_name=provider.provider_name,
                        model_name=step_result.raw_model_name or provider.model,
                        total_input_tokens=total_input_tokens,
                        total_output_tokens=total_output_tokens,
                        total_tokens=total_input_tokens + total_output_tokens,
                    )

                tool_call_count += 1
                if tool_call_count > settings.max_agent_tool_calls:
                    raise AgentTerminated(
                        "max_tool_calls_exceeded",
                        f"Tool-call budget {settings.max_agent_tool_calls} exceeded",
                    )

                outcome = await governed_tool_call(
                    db,
                    agent_run_id=agent_run_id,
                    mcp_client=mcp_client,
                    tool_name=call.name,
                    arguments=call.arguments,
                    scoped_campaign_id=campaign_id,
                )
                tool_outcomes.append(outcome)
                tools_selected.append(call.name)

                result_payload: dict[str, Any] = dict(outcome.data)
                if outcome.ok:
                    evidence_id = f"E{next_evidence_number}"
                    next_evidence_number += 1
                    evidence_ledger[evidence_id] = EvidenceEntry(
                        id=evidence_id, tool_name=call.name, campaign_id=campaign_id, data=outcome.data
                    )
                    result_payload["evidence_id"] = evidence_id

                history.append(ToolResultTurn(tool_call_id=call.id, name=call.name, content=result_payload))

            raise AgentTerminated("max_steps_exceeded", f"Step budget {settings.max_agent_steps} exceeded without finishing")
    except MCPClientError as exc:
        raise AgentTerminated("mcp_unavailable", str(exc)) from exc


def _validate_diagnosis(arguments: dict[str, Any]) -> GovernedDiagnosis:
    try:
        return GovernedDiagnosis.model_validate(arguments)
    except ValidationError as exc:
        raise AgentTerminated("structured_output_failure", f"Finish call did not match the diagnosis schema: {exc}") from exc


def _grounded_causes(
    diagnosis: GovernedDiagnosis, evidence_ledger: dict[str, EvidenceEntry], campaign_id: int
) -> list[GovernedCause]:
    """Evidence discipline (bounded-loop side of it): drop any root cause whose
    evidence_ids are not ALL present in this run's ledger and scoped to this
    campaign. A partially-grounded cause is dropped entirely rather than
    silently trimmed, so a surviving cause's evidence_ids are exactly what the
    model cited - safe to render as-is."""
    grounded: list[GovernedCause] = []
    for cause in diagnosis.root_causes:
        valid = all(
            evidence_id in evidence_ledger and evidence_ledger[evidence_id].campaign_id == campaign_id
            for evidence_id in cause.evidence_ids
        )
        if valid:
            grounded.append(cause)
    return grounded
