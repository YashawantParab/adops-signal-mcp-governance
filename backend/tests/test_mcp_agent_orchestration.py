"""Tests for the POST /api/mcp/agent/run dispatcher (run_agent_orchestration):
which execution_mode and fallback_reason get persisted, and that observability
fields on AgentRun are only ever populated from real provider/loop output -
never fabricated - for both the primary llm_mcp_agent path and every
documented fallback trigger.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.mcp_governance_service as mcp_governance_service
from app.agent.mcp_client import DEFAULT_MCP_SERVER_DIR
from app.agent.providers.base import (
    FINISH_TOOL_NAME,
    LLMProvider,
    StepResult,
    StepUsage,
    ToolCall,
    ToolSpec,
    Turn,
)
from app.config import Settings
from app.database import Base
from app.models import AgentRun
from seed import build_seed_data

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
    "client_safe_brief": "Delivery is currently limited by a creative validation issue. We are correcting it and will resume scaling once resolved.",
}


class ScriptedProvider(LLMProvider):
    provider_name = "openai"

    def __init__(self, steps: list[ToolCall], *, available: bool = True, classify_decision: str | None = None, classify_confidence: float | None = 0.9) -> None:
        self._steps = list(steps)
        self._available = available
        self._calls = 0
        self._classify_decision = classify_decision
        self._classify_confidence = classify_confidence

    @property
    def model(self) -> str:
        return "scripted-model"

    @property
    def available(self) -> bool:
        return self._available

    def decide_next_step(
        self, *, system_prompt: str, initial_query: str, history: list[Turn], tools: list[ToolSpec]
    ) -> StepResult:
        call = self._steps[min(self._calls, len(self._steps) - 1)]
        self._calls += 1
        return StepResult(
            tool_call=call,
            usage=StepUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            raw_model_name="scripted-model",
        )

    def classify(self, *, system_prompt, payload, schema):
        from app.agent.providers.base import ClassificationResult

        if self._classify_decision is None:
            raise NotImplementedError("this test did not configure classify_decision - see test_gates.py")
        return ClassificationResult(
            decision=self._classify_decision, confidence=self._classify_confidence,
            raw_model_name="scripted-model", usage=StepUsage(input_tokens=5, output_tokens=2, total_tokens=7),
        )


def seeded_session(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'orchestration.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    data = build_seed_data()
    for key in ["advertisers", "publishers", "inventory_segments", "campaigns", "creatives", "vast_validation_errors"]:
        db.add_all(data[key])
        db.flush()
    db.commit()
    return db, database_url


def _settings(database_url: str, **overrides) -> Settings:
    base = dict(database_url=database_url, mcp_agent_enabled=True, agent_timeout_seconds=10.0)
    base.update(overrides)
    return Settings(**base)


def test_llm_mcp_agent_path_persists_real_observability_fields(tmp_path, monkeypatch):
    if not DEFAULT_MCP_SERVER_DIR.exists():
        import pytest

        pytest.skip("mcp-server/ is not present in this checkout")

    db, database_url = seeded_session(tmp_path)
    campaign = db.get(mcp_governance_service.Campaign, 1045)
    settings = _settings(database_url)
    provider = ScriptedProvider(
        steps=[
            ToolCall(id="call_1", name="get_vast_validation_summary", arguments={"campaign_id": 1045}),
            ToolCall(id="call_2", name=FINISH_TOOL_NAME, arguments=VALID_DIAGNOSIS),
        ]
    )
    monkeypatch.setattr(mcp_governance_service, "get_settings", lambda: settings)
    monkeypatch.setattr(mcp_governance_service, "get_llm_provider", lambda settings: provider)

    result = mcp_governance_service.run_agent_orchestration(db, "Why is this campaign underdelivering?", "1045")

    assert result.execution_mode == "llm_mcp_agent"
    assert result.fallback_reason is None
    assert result.llm_provider == "openai"
    assert result.model_name == "scripted-model"
    assert result.input_tokens == 20
    assert result.output_tokens == 10
    assert result.total_tokens == 30
    assert result.steps_used == 2
    assert result.max_steps == settings.max_agent_steps
    assert result.tools_selected == ["get_vast_validation_summary"]
    assert result.estimated_cost_usd is None  # never fabricated - neither provider SDK returns a $ cost here

    run = db.get(AgentRun, int(result.agent_run_id))
    assert run.execution_mode == "llm_mcp_agent"
    assert run.llm_provider == "openai"
    assert run.fallback_reason is None

    # Regression: the *read* path (GET /api/mcp/runs, /api/mcp/runs/{id}) must
    # reflect these fields too, not just the response returned at submit time -
    # a reviewer reloading the run detail page must see the real execution_mode.
    listed = next(item for item in mcp_governance_service.list_agent_runs(db) if item.id == run.id)
    assert listed.execution_mode == "llm_mcp_agent"
    assert listed.llm_provider == "openai"
    assert listed.model_name == "scripted-model"
    assert listed.steps_used == 2

    detail = mcp_governance_service.get_agent_run_detail(db, run.id)
    assert detail.execution_mode == "llm_mcp_agent"
    assert detail.total_tokens == 30
    assert detail.fallback_reason is None

    # Phase 2: the three primary gate points ran and persisted real decisions.
    # decision_gate_provider defaults to "rules" (no key needed), so RuleGate
    # both answered them and - for risk_routing specifically - is a pure
    # pass-through of the deterministic rule floor (by construction), meaning
    # approval/blocked semantics are unchanged from before gates existed.
    points = {item.decision_point for item in result.gate_decisions}
    assert points == {"evidence_verification", "risk_routing", "client_safe_brief"}
    assert all(item.gate_type == "rules" for item in result.gate_decisions)

    risk_routing_decision = next(item for item in result.gate_decisions if item.decision_point == "risk_routing")
    assert risk_routing_decision.rule_floor == risk_routing_decision.final_decision  # RuleGate is a no-op on the floor

    evidence_decision = next(item for item in result.gate_decisions if item.decision_point == "evidence_verification")
    assert evidence_decision.decision in ("supported", "uncertain")  # the cited evidence genuinely backs the cause

    assert result.client_safe_brief_status == "safe"
    assert result.client_safe_brief == VALID_DIAGNOSIS["client_safe_brief"]

    detail_points = {item.decision_point for item in detail.gate_decisions}
    assert detail_points == points  # read path (GET .../runs/{id}) reflects the same gate decisions


def test_missing_provider_key_falls_back_to_deterministic(tmp_path, monkeypatch):
    db, database_url = seeded_session(tmp_path)
    settings = _settings(database_url)
    provider = ScriptedProvider(steps=[], available=False)
    monkeypatch.setattr(mcp_governance_service, "get_settings", lambda: settings)
    monkeypatch.setattr(mcp_governance_service, "get_llm_provider", lambda settings: provider)

    result = mcp_governance_service.run_agent_orchestration(db, "Why is this campaign underdelivering?", "1045")

    assert result.execution_mode == "deterministic_fallback"
    assert result.fallback_reason == "missing_provider_key"
    assert result.llm_provider is None

    run = db.get(AgentRun, int(result.agent_run_id))
    assert run.execution_mode == "deterministic_fallback"
    assert run.fallback_reason == "missing_provider_key"


def test_mcp_agent_disabled_setting_falls_back_without_calling_provider(tmp_path, monkeypatch):
    db, database_url = seeded_session(tmp_path)
    settings = _settings(database_url, mcp_agent_enabled=False)

    def _fail(*args, **kwargs):
        raise AssertionError("get_llm_provider must not be called when mcp_agent_enabled is False")

    monkeypatch.setattr(mcp_governance_service, "get_settings", lambda: settings)
    monkeypatch.setattr(mcp_governance_service, "get_llm_provider", _fail)

    result = mcp_governance_service.run_agent_orchestration(db, "Why is this campaign underdelivering?", "1045")

    assert result.execution_mode == "deterministic_fallback"
    assert result.fallback_reason == "mcp_agent_disabled"


def test_mcp_unavailable_falls_back_to_deterministic(tmp_path, monkeypatch):
    db, database_url = seeded_session(tmp_path)
    settings = _settings(database_url, mcp_server_command="definitely-not-a-real-executable")
    provider = ScriptedProvider(steps=[ToolCall(id="call_1", name=FINISH_TOOL_NAME, arguments=VALID_DIAGNOSIS)])
    monkeypatch.setattr(mcp_governance_service, "get_settings", lambda: settings)
    monkeypatch.setattr(mcp_governance_service, "get_llm_provider", lambda settings: provider)

    result = mcp_governance_service.run_agent_orchestration(db, "Why is this campaign underdelivering?", "1045")

    assert result.execution_mode == "deterministic_fallback"
    assert result.fallback_reason == "mcp_unavailable"


def test_risk_routing_gate_escalation_actually_blocks_a_low_risk_campaign(tmp_path, monkeypatch):
    """Proves gate escalation isn't just a value computed and ignored: with
    DECISION_GATE_PROVIDER=llm and a gate that says "block" for a campaign
    whose deterministic rule floor is only auto_recommend, the run must
    actually end up blocked=True with a BlockedAction row - not merely record
    the gate's opinion."""
    if not DEFAULT_MCP_SERVER_DIR.exists():
        import pytest

        pytest.skip("mcp-server/ is not present in this checkout")

    db, database_url = seeded_session(tmp_path)
    settings = _settings(database_url, decision_gate_provider="llm")
    provider = ScriptedProvider(
        steps=[
            ToolCall(id="call_1", name="get_vast_validation_summary", arguments={"campaign_id": 1047}),
            ToolCall(id="call_2", name=FINISH_TOOL_NAME, arguments=VALID_DIAGNOSIS),
        ],
        classify_decision="block",
        classify_confidence=0.9,
    )
    import app.gates as gates_module

    monkeypatch.setattr(mcp_governance_service, "get_settings", lambda: settings)
    monkeypatch.setattr(mcp_governance_service, "get_llm_provider", lambda settings: provider)
    # get_decision_gate_chain (app.gates) resolves get_llm_provider from its OWN
    # module namespace, independent of mcp_governance_service's imported name -
    # both must be patched for the scripted provider to answer gate decisions too.
    monkeypatch.setattr(gates_module, "get_llm_provider", lambda settings: provider)

    result = mcp_governance_service.run_agent_orchestration(db, "Is LuxeHome healthy and pacing on plan?", "1047")

    assert result.execution_mode == "llm_mcp_agent"
    assert result.risk_level == "LOW"  # the deterministic rule engine's own read is unchanged
    assert result.blocked is True  # but the gate escalated final routing to block
    assert result.approval_required is True

    routing_decision = next(item for item in result.gate_decisions if item.decision_point == "risk_routing")
    assert routing_decision.rule_floor == "auto_recommend"
    assert routing_decision.decision == "block"
    assert routing_decision.final_decision == "block"
    assert routing_decision.gate_type == "llm"

    run = db.get(AgentRun, int(result.agent_run_id))
    from app.models import BlockedAction

    assert db.query(BlockedAction).filter_by(agent_run_id=run.id).count() == 1
