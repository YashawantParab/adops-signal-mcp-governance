"""Tests for the DecisionGate abstraction (app.gates): RuleGate behavior, the
rule-floor-can-only-escalate guarantee, low-confidence conservative routing,
the jev->llm->rules fallback chain, LLMGate structural correctness (scripted
provider, no live key needed), and JevGate's honest unavailability without
TYPESAFE_API_KEY. No live external API calls anywhere in this file.
"""
from __future__ import annotations

import asyncio

import pytest

from app.agent.providers.base import ClassificationResult, LLMProvider, ProviderError, StepUsage
from app.config import Settings
from app.gates import decide_with_fallback, get_decision_gate_chain
from app.gates.base import DecisionRequest, GateUnavailable, apply_rule_floor
from app.gates.decision_points import (
    RISK_ROUTING_DECISIONS,
    client_safe_brief_check,
    evidence_verification,
    risk_routing,
)
from app.gates.jev_gate import JevGate
from app.gates.llm_gate import LLMGate
from app.gates.rule_gate import RuleGate


def run(coro):
    return asyncio.run(coro)


# --- apply_rule_floor: the non-negotiable guarantee -------------------------


@pytest.mark.parametrize(
    "rule_floor,gate_decision,expected",
    [
        ("require_approval", "auto_recommend", "require_approval"),  # gate tries to downgrade -> blocked
        ("block", "require_approval", "block"),  # gate tries to downgrade -> blocked
        ("block", "auto_recommend", "block"),  # gate tries to downgrade two levels -> blocked
        ("auto_recommend", "block", "block"),  # gate escalates -> allowed
        ("auto_recommend", "require_approval", "require_approval"),  # gate escalates -> allowed
        ("require_approval", "require_approval", "require_approval"),  # gate agrees -> no change
    ],
)
def test_rule_floor_can_only_be_escalated_never_downgraded(rule_floor, gate_decision, expected):
    result = apply_rule_floor(rule_floor, gate_decision, confidence=0.99, confidence_threshold=0.6)
    assert result == expected


def test_low_confidence_forces_at_least_require_approval():
    # Gate says auto_recommend, floor also allows auto_recommend, but confidence is
    # below threshold - must still not resolve to auto_recommend.
    result = apply_rule_floor("auto_recommend", "auto_recommend", confidence=0.2, confidence_threshold=0.6)
    assert result == "require_approval"


def test_high_confidence_auto_recommend_is_allowed_when_floor_permits():
    result = apply_rule_floor("auto_recommend", "auto_recommend", confidence=0.95, confidence_threshold=0.6)
    assert result == "auto_recommend"


def test_low_confidence_never_downgrades_a_block_floor():
    result = apply_rule_floor("block", "auto_recommend", confidence=0.99, confidence_threshold=0.6)
    assert result == "block"


# --- RuleGate ----------------------------------------------------------------


def test_rule_gate_risk_routing_returns_the_floor_itself():
    gate = RuleGate()
    request = DecisionRequest(
        decision_point="risk_routing", run_id=1, campaign_id=1045, state={},
        allowed_decisions=RISK_ROUTING_DECISIONS, rule_floor="require_approval",
    )
    result = run(gate.decide(request))
    assert result.decision == "require_approval"
    assert result.confidence == 1.0
    assert result.gate_type == "rules"


def test_rule_gate_client_safe_brief_blocks_forbidden_terms():
    gate = RuleGate()
    request = DecisionRequest(
        decision_point="client_safe_brief", run_id=1, campaign_id=1045,
        state={"brief_text": "We adjusted delivery after reviewing the publisher floor with the team."},
        allowed_decisions=["safe", "needs_review", "block"],
    )
    result = run(gate.decide(request))
    assert result.decision == "block"


def test_rule_gate_client_safe_brief_allows_clean_text():
    gate = RuleGate()
    request = DecisionRequest(
        decision_point="client_safe_brief", run_id=1, campaign_id=1045,
        state={"brief_text": "Delivery is recovering after a creative update; no further action needed."},
        allowed_decisions=["safe", "needs_review", "block"],
    )
    result = run(gate.decide(request))
    assert result.decision == "safe"


def test_rule_gate_evidence_verification_unsupported_when_no_overlap():
    gate = RuleGate()
    request = DecisionRequest(
        decision_point="evidence_verification", run_id=1, campaign_id=1045,
        state={"cause_text": "Creative was rejected for policy violation", "evidence_text": "pacing snapshot 61 percent delivered"},
        allowed_decisions=["supported", "unsupported", "uncertain"],
    )
    result = run(gate.decide(request))
    assert result.decision == "unsupported"


def test_rule_gate_evidence_verification_supported_with_overlap():
    gate = RuleGate()
    request = DecisionRequest(
        decision_point="evidence_verification", run_id=1, campaign_id=1045,
        state={
            "cause_text": "VAST validation errors are suppressing delivery for the creative",
            "evidence_text": "vast validation errors detected on creative, error count 3",
        },
        allowed_decisions=["supported", "unsupported", "uncertain"],
    )
    result = run(gate.decide(request))
    assert result.decision == "supported"


# --- JevGate: honest unavailability -----------------------------------------


def test_jev_gate_unavailable_without_api_key():
    gate = JevGate(Settings(typesafe_api_key=None))
    assert gate.available is False
    with pytest.raises(GateUnavailable):
        run(gate.decide(DecisionRequest(
            decision_point="risk_routing", run_id=1, campaign_id=1045, state={},
            allowed_decisions=RISK_ROUTING_DECISIONS, rule_floor="auto_recommend",
        )))


def test_jev_gate_unavailable_without_sdk_installed_even_with_key():
    # typesafe-sdk is not in requirements.txt yet (pending approval) - even with a
    # key configured, the gate must report unavailable rather than crash on import.
    gate = JevGate(Settings(typesafe_api_key="fake-key-for-test"))
    assert gate.available is False


# --- LLMGate: structural correctness with a scripted provider ---------------


class ScriptedClassifyProvider(LLMProvider):
    provider_name = "openai"

    def __init__(self, *, decision: str, confidence: float | None, available: bool = True, error: Exception | None = None) -> None:
        self._decision = decision
        self._confidence = confidence
        self._available = available
        self._error = error

    @property
    def model(self) -> str:
        return "scripted-model"

    @property
    def available(self) -> bool:
        return self._available

    def decide_next_step(self, **kwargs):
        raise NotImplementedError("not exercised by gate tests")

    def classify(self, *, system_prompt, payload, schema):
        if self._error is not None:
            raise self._error
        return ClassificationResult(
            decision=self._decision, confidence=self._confidence, raw_model_name="scripted-model",
            usage=StepUsage(input_tokens=8, output_tokens=4, total_tokens=12),
        )


def test_llm_gate_returns_structured_decision():
    provider = ScriptedClassifyProvider(decision="require_approval", confidence=0.82)
    gate = LLMGate(provider)
    result = run(gate.decide(DecisionRequest(
        decision_point="risk_routing", run_id=1, campaign_id=1045, state={"proposed_action": "expand inventory"},
        allowed_decisions=RISK_ROUTING_DECISIONS, rule_floor="auto_recommend",
    )))
    assert result.decision == "require_approval"
    assert result.confidence == 0.82
    assert result.gate_type == "llm"
    assert result.provider == "openai"


def test_llm_gate_unavailable_without_provider_key():
    provider = ScriptedClassifyProvider(decision="block", confidence=0.9, available=False)
    gate = LLMGate(provider)
    with pytest.raises(GateUnavailable):
        run(gate.decide(DecisionRequest(
            decision_point="risk_routing", run_id=1, campaign_id=1045, state={},
            allowed_decisions=RISK_ROUTING_DECISIONS, rule_floor="auto_recommend",
        )))


def test_llm_gate_raises_gate_unavailable_on_provider_error():
    provider = ScriptedClassifyProvider(decision="block", confidence=0.9, error=ProviderError("malformed json"))
    gate = LLMGate(provider)
    with pytest.raises(GateUnavailable):
        run(gate.decide(DecisionRequest(
            decision_point="risk_routing", run_id=1, campaign_id=1045, state={},
            allowed_decisions=RISK_ROUTING_DECISIONS, rule_floor="auto_recommend",
        )))


def test_llm_gate_falls_back_to_first_allowed_decision_for_unlisted_answer():
    provider = ScriptedClassifyProvider(decision="not_a_real_option", confidence=0.9)
    gate = LLMGate(provider)
    result = run(gate.decide(DecisionRequest(
        decision_point="risk_routing", run_id=1, campaign_id=1045, state={},
        allowed_decisions=RISK_ROUTING_DECISIONS, rule_floor="auto_recommend",
    )))
    assert result.decision == RISK_ROUTING_DECISIONS[0]
    assert result.reason is not None


# --- decide_with_fallback: explicit, documented chain order -----------------


def test_fallback_chain_skips_unavailable_jev_and_uses_rules():
    settings = Settings(decision_gate_provider="jev", typesafe_api_key=None)
    chain = get_decision_gate_chain(settings)
    assert [gate.gate_type for gate in chain] == ["jev", "llm", "rules"]

    request = DecisionRequest(
        decision_point="risk_routing", run_id=1, campaign_id=1045, state={},
        allowed_decisions=RISK_ROUTING_DECISIONS, rule_floor="require_approval",
    )
    result = run(decide_with_fallback(request, chain))
    assert result.gate_type == "rules"  # jev and llm both unavailable (no keys)
    assert "skipped_gates" in result.metadata
    skipped_types = [entry["gate_type"] for entry in result.metadata["skipped_gates"]]
    assert skipped_types == ["jev", "llm"]


def test_rules_only_provider_never_calls_llm_or_jev():
    settings = Settings(decision_gate_provider="rules")
    chain = get_decision_gate_chain(settings)
    assert [gate.gate_type for gate in chain] == ["rules"]


# --- decision_points: end-to-end with RuleGate only (deterministic, no keys) -


def test_risk_routing_decision_point_never_downgrades():
    settings = Settings(decision_gate_provider="rules")
    chain = get_decision_gate_chain(settings)
    outcome = run(risk_routing(
        run_id=1, campaign_id=1045, rule_floor="require_approval",
        proposed_action="Expand eligible CTV inventory", evidence_summary={}, chain=chain, settings=settings,
    ))
    assert outcome.final_routing == "require_approval"
    assert outcome.gate_result.gate_type == "rules"


def test_evidence_verification_decision_point_marks_unsupported():
    settings = Settings(decision_gate_provider="rules")
    chain = get_decision_gate_chain(settings)
    result = run(evidence_verification(
        run_id=1, campaign_id=1045, cause_text="Bid price below floor is limiting wins",
        evidence_text="creative rejected, VAST error count 4", chain=chain,
    ))
    assert result.decision == "unsupported"


def test_client_safe_brief_decision_point_blocks_leaky_text():
    settings = Settings(decision_gate_provider="rules")
    chain = get_decision_gate_chain(settings)
    result = run(client_safe_brief_check(
        run_id=1, campaign_id=1045, brief_text="Publisher floor price was the loss reason, per sql_analysis_tool output.",
        chain=chain,
    ))
    assert result.decision == "block"
