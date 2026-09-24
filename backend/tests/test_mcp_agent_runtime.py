"""Integration tests for the governed MCP agent's bounded step loop
(app.agent.mcp_agent_runtime), driven against the REAL standalone MCP server
over real stdio (same server proven in test_mcp_client_integration.py), with a
scripted fake LLM provider standing in for the network call. This proves the
loop's governance, bounding, and evidence-integrity behavior end to end
without needing a live OpenAI/Anthropic key - the provider boundary is the
only thing faked; MCP, governance, and persistence are all real.
"""
from __future__ import annotations

import time

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.agent.mcp_agent_runtime import AgentTerminated, run_governed_mcp_agent
from app.agent.mcp_client import DEFAULT_MCP_SERVER_DIR
from app.agent.providers.base import (
    FINISH_TOOL_NAME,
    LLMProvider,
    ProviderError,
    StepResult,
    StepUsage,
    ToolCall,
    ToolSpec,
    Turn,
)
from app.config import Settings
from app.database import Base
from app.models import AgentRun, MCPToolCall
from seed import build_seed_data

pytestmark = pytest.mark.skipif(
    not DEFAULT_MCP_SERVER_DIR.exists(), reason="mcp-server/ is not present in this checkout"
)

VALID_DIAGNOSIS = {
    "diagnosis": "Campaign 1045 is behind pacing because of a persistent VAST validation issue on its lead creative.",
    "root_causes": [
        {
            "cause": "VAST validation errors are suppressing delivery",
            "impact": "High",
            "evidence_ids": ["E1"],
            "recommendation_title": "Fix and revalidate the failing creative",
            "recommendation_description": "Correct the VAST tag issue and resubmit the creative for validation before scaling spend.",
            "expected_impact": "High",
            "risk_level": "Medium",
        }
    ],
    "confidence_score": 0.8,
    "human_approval_required": True,
}


class ScriptedProvider(LLMProvider):
    """Replays a fixed sequence of tool calls, one per `decide_next_step` call.

    Standing in for a real LLM: the point under test is the governed loop
    around the provider (MCP dispatch, bounds, evidence grounding), not the
    provider's own network call.
    """

    provider_name = "openai"

    def __init__(self, steps: list[ToolCall], *, sleep_seconds: float = 0.0, error: Exception | None = None) -> None:
        self._steps = list(steps)
        self._sleep_seconds = sleep_seconds
        self._error = error
        self._calls = 0
        self.offered_tools: list[list[ToolSpec]] = []

    @property
    def model(self) -> str:
        return "scripted-model"

    @property
    def available(self) -> bool:
        return True

    def decide_next_step(
        self, *, system_prompt: str, initial_query: str, history: list[Turn], tools: list[ToolSpec]
    ) -> StepResult:
        if self._sleep_seconds:
            time.sleep(self._sleep_seconds)
        if self._error is not None:
            raise self._error
        self.offered_tools.append(tools)
        call = self._steps[min(self._calls, len(self._steps) - 1)]
        self._calls += 1
        return StepResult(
            tool_call=call,
            usage=StepUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            raw_model_name="scripted-model",
        )


def seeded_session_and_run(tmp_path, campaign_id: int = 1045):
    database_url = f"sqlite:///{tmp_path / 'agent_runtime.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    data = build_seed_data()
    for key in ["advertisers", "publishers", "inventory_segments", "campaigns", "creatives", "vast_validation_errors"]:
        db.add_all(data[key])
        db.flush()
    db.commit()

    run = AgentRun(
        user_query="Why is this campaign underdelivering?",
        campaign_id=campaign_id,
        status="running",
        risk_level="LOW",
        risk_score=0.0,
        final_recommendation="",
        approval_required=False,
        execution_mode="llm_mcp_agent",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return db, run, database_url


def _settings(database_url: str, **overrides) -> Settings:
    base = dict(
        database_url=database_url,
        max_agent_steps=6,
        max_agent_tool_calls=6,
        max_agent_tokens=20000,
        agent_timeout_seconds=10.0,
    )
    base.update(overrides)
    return Settings(**base)


def test_agent_dynamically_selects_a_real_mcp_tool_then_finishes_with_grounded_evidence(tmp_path):
    """The primary path: the model is offered every real MCP tool plus `finish`,
    picks one dynamically, gets a governed+MCP-executed result back tagged with
    an evidence_id, and cites that real evidence_id in its final diagnosis."""
    db, run, database_url = seeded_session_and_run(tmp_path)
    provider = ScriptedProvider(
        steps=[
            ToolCall(id="call_1", name="get_vast_validation_summary", arguments={"campaign_id": 1045}),
            ToolCall(id="call_2", name=FINISH_TOOL_NAME, arguments=VALID_DIAGNOSIS),
        ]
    )

    outcome = _run(db, run, provider, campaign_id=1045, settings=_settings(database_url))

    assert outcome.tools_selected == ["get_vast_validation_summary"]
    assert list(outcome.evidence_ledger.keys()) == ["E1"]
    assert outcome.grounded_root_causes  # the cited E1 was real evidence from this run
    assert outcome.provider_name == "openai"
    assert outcome.total_input_tokens == 20  # two provider steps x 10 input tokens each
    assert outcome.total_output_tokens == 10  # two provider steps x 5 output tokens each

    # The set of tools offered to the model included every real MCP tool, not a
    # hardcoded subset - dynamic selection, not a fixed sequence.
    offered_names = {tool.name for tool in provider.offered_tools[0]}
    assert {"get_campaign_health", "get_campaign_pacing", "get_vast_validation_summary", FINISH_TOOL_NAME}.issubset(
        offered_names
    )

    row = db.execute(select(MCPToolCall).where(MCPToolCall.agent_run_id == run.id)).scalar_one()
    assert row.status == "success"
    assert row.tool_name == "get_vast_validation_summary"


def test_unknown_tool_is_governed_denied_and_never_reaches_mcp_but_run_continues(tmp_path):
    db, run, database_url = seeded_session_and_run(tmp_path)
    provider = ScriptedProvider(
        steps=[
            ToolCall(id="call_1", name="delete_campaign", arguments={"campaign_id": 1045}),
            ToolCall(id="call_2", name="get_vast_validation_summary", arguments={"campaign_id": 1045}),
            ToolCall(id="call_3", name=FINISH_TOOL_NAME, arguments=VALID_DIAGNOSIS),
        ]
    )

    outcome = _run(db, run, provider, campaign_id=1045, settings=_settings(database_url))

    assert outcome.tools_selected == ["delete_campaign", "get_vast_validation_summary"]
    denied, allowed = outcome.tool_outcomes
    assert denied.ok is False
    assert denied.error_category == "UNKNOWN_TOOL"
    assert allowed.ok is True
    # The denied call never produced evidence - only the allowed one did.
    assert list(outcome.evidence_ledger.keys()) == ["E1"]

    rows = list(db.execute(select(MCPToolCall).where(MCPToolCall.agent_run_id == run.id)).scalars())
    assert {row.status for row in rows} == {"denied", "success"}


def test_out_of_scope_tool_call_is_governed_denied(tmp_path):
    db, run, database_url = seeded_session_and_run(tmp_path, campaign_id=1045)
    provider = ScriptedProvider(
        steps=[
            ToolCall(id="call_1", name="get_campaign_health", arguments={"campaign_id": 1046}),
            ToolCall(id="call_2", name="get_vast_validation_summary", arguments={"campaign_id": 1045}),
            ToolCall(id="call_3", name=FINISH_TOOL_NAME, arguments=VALID_DIAGNOSIS),
        ]
    )

    outcome = _run(db, run, provider, campaign_id=1045, settings=_settings(database_url))

    out_of_scope, allowed = outcome.tool_outcomes
    assert out_of_scope.ok is False
    assert out_of_scope.error_category == "OUT_OF_SCOPE"
    assert allowed.ok is True


def test_fabricated_evidence_id_is_rejected(tmp_path):
    db, run, database_url = seeded_session_and_run(tmp_path)
    fabricated = dict(VALID_DIAGNOSIS, root_causes=[dict(VALID_DIAGNOSIS["root_causes"][0], evidence_ids=["E99"])])
    provider = ScriptedProvider(steps=[ToolCall(id="call_1", name=FINISH_TOOL_NAME, arguments=fabricated)])

    with pytest.raises(AgentTerminated) as excinfo:
        _run(db, run, provider, campaign_id=1045, settings=_settings(database_url))
    assert excinfo.value.reason_code == "no_evidence_grounded_causes"


def test_max_tool_calls_exceeded_terminates_run(tmp_path):
    db, run, database_url = seeded_session_and_run(tmp_path)
    provider = ScriptedProvider(
        steps=[ToolCall(id=f"call_{i}", name="get_campaign_health", arguments={"campaign_id": 1045}) for i in range(10)]
    )

    with pytest.raises(AgentTerminated) as excinfo:
        _run(
            db,
            run,
            provider,
            campaign_id=1045,
            settings=_settings(database_url, max_agent_steps=10, max_agent_tool_calls=2),
        )
    assert excinfo.value.reason_code == "max_tool_calls_exceeded"


def test_max_steps_exceeded_terminates_run(tmp_path):
    db, run, database_url = seeded_session_and_run(tmp_path)
    provider = ScriptedProvider(
        steps=[ToolCall(id=f"call_{i}", name="get_campaign_health", arguments={"campaign_id": 1045}) for i in range(10)]
    )

    with pytest.raises(AgentTerminated) as excinfo:
        _run(
            db,
            run,
            provider,
            campaign_id=1045,
            settings=_settings(database_url, max_agent_steps=2, max_agent_tool_calls=50),
        )
    assert excinfo.value.reason_code == "max_steps_exceeded"


def test_provider_error_terminates_run(tmp_path):
    db, run, database_url = seeded_session_and_run(tmp_path)
    provider = ScriptedProvider(steps=[], error=ProviderError("simulated auth failure"))

    with pytest.raises(AgentTerminated) as excinfo:
        _run(db, run, provider, campaign_id=1045, settings=_settings(database_url))
    assert excinfo.value.reason_code == "provider_error"


def test_slow_provider_call_is_preempted_by_agent_timeout(tmp_path):
    """Regression test: provider.decide_next_step is a blocking synchronous SDK
    call. It must run off the event loop (see mcp_agent_runtime._run_loop) so
    AGENT_TIMEOUT_SECONDS can actually preempt it instead of only noticing the
    overrun once the blocking call happens to return."""
    db, run, database_url = seeded_session_and_run(tmp_path)
    provider = ScriptedProvider(steps=[], sleep_seconds=2.0)

    started = time.perf_counter()
    with pytest.raises(AgentTerminated) as excinfo:
        _run(db, run, provider, campaign_id=1045, settings=_settings(database_url, agent_timeout_seconds=0.3))
    elapsed = time.perf_counter() - started

    assert excinfo.value.reason_code == "timeout"
    assert elapsed < 1.5  # well under the provider's 2s sleep - the timeout actually preempted it


def _run(db, run, provider, *, campaign_id: int, settings: Settings):
    import asyncio

    return asyncio.run(
        run_governed_mcp_agent(
            db,
            agent_run_id=run.id,
            campaign_id=campaign_id,
            user_query="Why is this campaign underdelivering?",
            provider=provider,
            settings=settings,
        )
    )
