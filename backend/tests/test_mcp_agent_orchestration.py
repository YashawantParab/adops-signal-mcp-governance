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
}


class ScriptedProvider(LLMProvider):
    provider_name = "openai"

    def __init__(self, steps: list[ToolCall], *, available: bool = True) -> None:
        self._steps = list(steps)
        self._available = available
        self._calls = 0

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
