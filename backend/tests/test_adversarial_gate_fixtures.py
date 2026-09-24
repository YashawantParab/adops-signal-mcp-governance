"""Deterministic, CI-safe coverage of the adversarial fixtures in
evals/adversarial_cases.json (Phase 2G.D). Only exercises RuleGate and
apply_rule_floor directly - no live LLM/Jev calls. The live, multi-gate
comparison across all fixtures (including LLMGate/JevGate where configured)
is a separate MANUAL command: `python -m evals.gate_evaluation` - see that
module's docstring for why it must never run in standard CI.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.gates.base import DecisionRequest, apply_rule_floor
from app.gates.rule_gate import RuleGate

FIXTURES_PATH = Path(__file__).resolve().parents[1] / "evals" / "adversarial_cases.json"
FIXTURES = json.loads(FIXTURES_PATH.read_text())


def _allowed_decisions_for(decision_point: str) -> list[str]:
    from app.gates.decision_points import (
        CLIENT_SAFE_BRIEF_DECISIONS,
        PROMPT_INJECTION_DECISIONS,
        RISK_QUEUE_CATEGORIES,
        RISK_ROUTING_DECISIONS,
        TOOL_SCOPE_DECISIONS,
    )

    return {
        "risk_routing": RISK_ROUTING_DECISIONS,
        "evidence_verification": ["supported", "unsupported", "uncertain"],
        "client_safe_brief": CLIENT_SAFE_BRIEF_DECISIONS,
        "tool_scope": TOOL_SCOPE_DECISIONS,
        "prompt_injection_screen": PROMPT_INJECTION_DECISIONS,
        "risk_queue_triage": RISK_QUEUE_CATEGORIES,
    }[decision_point]


def test_adversarial_fixture_file_has_all_eight_documented_categories():
    categories = {case["category"] for case in FIXTURES}
    assert categories == {
        "prompt_injection_in_policy_document",
        "ambiguous_campaign_no_single_root_cause",
        "mcp_tool_returns_error",
        "attempted_out_of_scope_tool",
        "fabricated_evidence_id",
        "low_confidence_gate_decision",
        "llm_proposes_action_below_rule_floor",
        "client_brief_unsupported_publisher_blame",
    }


@pytest.mark.parametrize("case", [c for c in FIXTURES if c.get("decision_point") and "expected_rule_gate_decision" in c], ids=lambda c: c["id"])
def test_rule_gate_adversarial_fixture(case):
    gate = RuleGate()
    request = DecisionRequest(
        decision_point=case["decision_point"],
        run_id=1,
        campaign_id=case["state"].get("scoped_campaign_id") or case["state"].get("campaign_id"),
        state=case["state"],
        allowed_decisions=_allowed_decisions_for(case["decision_point"]),
        rule_floor=case["state"].get("rule_floor"),
    )
    result = asyncio.run(gate.decide(request))
    assert result.decision == case["expected_rule_gate_decision"], (
        f"{case['id']} ({case['category']}): expected {case['expected_rule_gate_decision']!r}, got {result.decision!r}"
    )


@pytest.mark.parametrize("case", [c for c in FIXTURES if "expected_final_routing" in c], ids=lambda c: c["id"])
def test_rule_floor_adversarial_fixture(case):
    state = case["state"]
    final = apply_rule_floor(
        state["rule_floor"], state["gate_decision"], confidence=state["confidence"], confidence_threshold=0.6
    )
    assert final == case["expected_final_routing"], f"{case['id']} ({case['category']}): expected {case['expected_final_routing']!r}, got {final!r}"


def test_client_brief_blame_fixture_documents_rule_gate_limitation():
    """A08 is intentionally NOT a pass/fail claim that RuleGate catches this -
    it documents, and locks in, the honest limitation: RuleGate cannot detect
    unsupported blame of a named partner from keyword matching alone."""
    case = next(c for c in FIXTURES if c["id"] == "A08")
    assert "rule_gate_limitation" in case
    gate = RuleGate()
    request = DecisionRequest(
        decision_point="client_safe_brief", run_id=1, campaign_id=None,
        state=case["state"], allowed_decisions=["safe", "needs_review", "block"],
    )
    result = asyncio.run(gate.decide(request))
    assert result.decision == "safe"  # documents the miss, does not claim it is correct
