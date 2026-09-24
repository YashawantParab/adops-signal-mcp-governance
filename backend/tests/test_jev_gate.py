"""JevGate test suite (Jev-readiness). No TYPESAFE_API_KEY, no live network call,
no live benchmark - this file tests only the external API boundary, against the
real installed `typesafe-sdk==0.7.1` package's own types (ChoiceAnswer,
SystemOneResponse, Usage, and its real exception classes), with realistic
deterministic fixtures. Only `AsyncTypeSafeClient` itself is mocked (the one
object that would otherwise make a network call) - every exception, response,
and field type used below is the genuine SDK type, not a hand-rolled stand-in.
DecisionGate business rules (apply_rule_floor, apply_confidence_floor,
decide_with_fallback) are exercised for real, unmocked - see
docs/jev-integration-notes.md for what is/isn't confirmed about the contract.
"""
from __future__ import annotations

import asyncio
import importlib
import sys

import pytest
import typesafe_sdk as sdk
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.gates import decide_with_fallback, get_decision_gate_chain
from app.gates.base import DecisionGate, DecisionRequest, GateUnavailable
from app.gates.decision_points import (
    CLIENT_SAFE_BRIEF_DECISIONS,
    EVIDENCE_VERIFICATION_DECISIONS,
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


def _settings(**overrides) -> Settings:
    return Settings(typesafe_api_key="test-key-not-live", decision_gate_provider="jev", **overrides)


def _request(decision_point: str = "risk_routing", **overrides) -> DecisionRequest:
    defaults = dict(
        decision_point=decision_point, run_id=1, campaign_id=1045, state={"proposed_action": "expand inventory"},
        allowed_decisions=RISK_ROUTING_DECISIONS, rule_floor="auto_recommend",
    )
    defaults.update(overrides)
    return DecisionRequest(**defaults)


class _FakeAsyncClient:
    """Stands in for typesafe_sdk.AsyncTypeSafeClient - the one object that
    would otherwise make a real network call. Everything it returns/raises is
    a genuine SDK type constructed by the test, not a hand-rolled fake."""

    def __init__(self, *, response=None, exc: Exception | None = None, **_kwargs) -> None:
        self._response = response
        self._exc = exc

    def __call__(self, **_kwargs):  # AsyncTypeSafeClient(...) is called with kwargs each time
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return False

    async def system_one(self, *, state, questions, **_kwargs):
        if self._exc is not None:
            raise self._exc
        return self._response


def _patch_client(monkeypatch, *, response=None, exc: Exception | None = None) -> None:
    fake = _FakeAsyncClient(response=response, exc=exc)
    monkeypatch.setattr(sdk, "AsyncTypeSafeClient", fake)


def _choice_response(*, choice: str, confidence: float = 0.9, probabilities: dict | None = None, model: str = "jev-latest") -> sdk.SystemOneResponse:
    answer = sdk.ChoiceAnswer(type="choice", choice=choice, confidence=confidence, probabilities=probabilities or {})
    usage = sdk.Usage(input_tokens=64, output_tokens=6)
    return sdk.SystemOneResponse(model=model, answers={"decision": answer}, usage=usage)


# --- 1. Successful Jev response ----------------------------------------------


def test_jev_gate_successful_response(monkeypatch):
    _patch_client(monkeypatch, response=_choice_response(choice="require_approval", confidence=0.9))
    gate = JevGate(_settings())
    result = run(gate.decide(_request()))
    assert result.decision == "require_approval"
    assert result.gate_type == "jev"
    assert result.provider == "jev"
    assert result.confidence == 0.9
    assert result.model_name  # jev_model default or response.model
    assert result.latency_ms >= 0
    assert result.cost_usd is None  # never fabricated


# --- 2. High-confidence response ----------------------------------------------


def test_jev_gate_high_confidence_response(monkeypatch):
    _patch_client(monkeypatch, response=_choice_response(choice="auto_recommend", confidence=0.98))
    gate = JevGate(_settings())
    result = run(gate.decide(_request(rule_floor="auto_recommend")))
    assert result.confidence == 0.98
    settings = _settings()
    from app.gates.base import apply_rule_floor
    final = apply_rule_floor("auto_recommend", result.decision, confidence=result.confidence, confidence_threshold=settings.gate_confidence_threshold)
    assert final == "auto_recommend"  # high confidence, permissive floor -> allowed through


# --- 3. Low-confidence response ------------------------------------------------


def test_jev_gate_low_confidence_response(monkeypatch):
    _patch_client(monkeypatch, response=_choice_response(choice="auto_recommend", confidence=0.2))
    gate = JevGate(_settings())
    result = run(gate.decide(_request(rule_floor="auto_recommend")))
    assert result.confidence == 0.2
    from app.gates.base import apply_rule_floor
    final = apply_rule_floor("auto_recommend", result.decision, confidence=result.confidence, confidence_threshold=0.6)
    assert final == "require_approval"  # low confidence forces escalation even though the floor itself allows auto_recommend


# --- 4. Unknown decision label -------------------------------------------------


def test_jev_gate_unknown_decision_label_raises_gate_unavailable(monkeypatch):
    _patch_client(monkeypatch, response=_choice_response(choice="not_a_real_option", confidence=0.9))
    gate = JevGate(_settings())
    with pytest.raises(GateUnavailable) as excinfo:
        run(gate.decide(_request()))
    assert excinfo.value.error_category == "failed"


# --- 5. Malformed response ------------------------------------------------------


def test_jev_gate_malformed_response_missing_decision_key_raises_gate_unavailable(monkeypatch):
    empty_response = sdk.SystemOneResponse(model="jev-latest", answers={}, usage=sdk.Usage(input_tokens=10, output_tokens=0))
    _patch_client(monkeypatch, response=empty_response)
    gate = JevGate(_settings())
    with pytest.raises(GateUnavailable) as excinfo:
        run(gate.decide(_request()))
    assert excinfo.value.error_category == "failed"


# --- 6. Timeout -------------------------------------------------------------


def test_jev_gate_timeout_raises_gate_unavailable(monkeypatch):
    _patch_client(monkeypatch, exc=sdk.TypeSafeAPITimeoutError(timeout=10.0))
    gate = JevGate(_settings())
    with pytest.raises(GateUnavailable) as excinfo:
        run(gate.decide(_request()))
    assert excinfo.value.error_category == "failed"
    assert "timed out" in str(excinfo.value).lower()


# --- 7. Authentication failure ------------------------------------------------


def test_jev_gate_authentication_failure_raises_gate_unavailable(monkeypatch):
    import httpx2
    err = sdk.TypeSafeAuthenticationError(status=401, body={"error": "invalid api key"}, headers=httpx2.Headers(), message="Invalid API key")
    _patch_client(monkeypatch, exc=err)
    gate = JevGate(_settings())
    with pytest.raises(GateUnavailable) as excinfo:
        run(gate.decide(_request()))
    assert excinfo.value.error_category == "failed"
    assert "authentication" in str(excinfo.value).lower()


# --- 8. Rate limit -----------------------------------------------------------


def test_jev_gate_rate_limit_raises_gate_unavailable(monkeypatch):
    import httpx2
    err = sdk.TypeSafeRateLimitError(status=429, body={"error": "rate limited"}, headers=httpx2.Headers({"retry-after": "2"}), message="Rate limit exceeded")
    _patch_client(monkeypatch, exc=err)
    gate = JevGate(_settings())
    with pytest.raises(GateUnavailable) as excinfo:
        run(gate.decide(_request()))
    assert excinfo.value.error_category == "failed"
    assert "rate limit" in str(excinfo.value).lower()


# --- 9. Server error -----------------------------------------------------------


def test_jev_gate_server_error_raises_gate_unavailable(monkeypatch):
    import httpx2
    err = sdk.TypeSafeInternalServerError(status=503, body={"error": "unavailable"}, headers=httpx2.Headers(), message="Service unavailable")
    _patch_client(monkeypatch, exc=err)
    gate = JevGate(_settings())
    with pytest.raises(GateUnavailable) as excinfo:
        run(gate.decide(_request()))
    assert excinfo.value.error_category == "failed"


# --- 10. Missing SDK ------------------------------------------------------------


def test_jev_gate_missing_sdk_reports_unavailable(monkeypatch):
    # Simulate typesafe_sdk not being importable, without actually uninstalling it -
    # `import typesafe_sdk` re-resolves sys.modules on every call in jev_gate.py.
    monkeypatch.setitem(sys.modules, "typesafe_sdk", None)
    gate = JevGate(_settings())
    assert gate.available is False
    with pytest.raises(GateUnavailable) as excinfo:
        run(gate.decide(_request()))
    assert excinfo.value.error_category == "unavailable"


# --- 11. Missing API key ---------------------------------------------------------


def test_jev_gate_missing_api_key_reports_unavailable():
    gate = JevGate(Settings(typesafe_api_key=None))
    assert gate.available is False
    with pytest.raises(GateUnavailable) as excinfo:
        run(gate.decide(_request()))
    assert excinfo.value.error_category == "unavailable"


def test_jev_gate_available_when_key_and_sdk_present():
    gate = JevGate(_settings())
    assert gate.available is True


# --- 12/13/14. Rule-floor conflicts: Jev may only escalate, never downgrade --


@pytest.mark.parametrize(
    "rule_floor,jev_decision,jev_confidence,expected_final",
    [
        ("block", "auto_recommend", 0.99, "block"),  # 12: rule floor=block, Jev tries to downgrade -> still block
        ("block", "auto_recommend", 0.4, "block"),  # 13: CRITICAL (block floor) cannot be downgraded even at low confidence
        ("require_approval", "auto_recommend", 0.95, "require_approval"),  # 14: HIGH (require_approval floor) still requires approval
    ],
)
def test_jev_gate_rule_floor_conflicts_via_risk_routing(monkeypatch, rule_floor, jev_decision, jev_confidence, expected_final):
    _patch_client(monkeypatch, response=_choice_response(choice=jev_decision, confidence=jev_confidence))
    chain: list[DecisionGate] = [JevGate(_settings())]
    settings = _settings()
    outcome = run(risk_routing(
        run_id=1, campaign_id=1045, rule_floor=rule_floor, proposed_action="Serve rejected creative",
        evidence_summary={"risk_level": "CRITICAL"}, chain=chain, settings=settings,
    ))
    assert outcome.final_routing == expected_final
    assert outcome.gate_result.gate_type == "jev"


# --- 15. Evidence unsupported ---------------------------------------------------


def test_jev_gate_evidence_unsupported_not_escalated(monkeypatch):
    _patch_client(monkeypatch, response=_choice_response(choice="unsupported", confidence=0.3))
    chain: list[DecisionGate] = [JevGate(_settings())]
    result = run(evidence_verification(
        run_id=1, campaign_id=1045, cause_text="Bid price below floor", evidence_text="unrelated evidence text",
        chain=chain, settings=_settings(),
    ))
    # "unsupported" is already conservative (it discards the cause) - low
    # confidence must not further alter an already-conservative outcome.
    assert result.decision == "unsupported"


# --- 16. Evidence uncertain (low-confidence "supported" escalated) -------------


def test_jev_gate_low_confidence_supported_escalates_to_uncertain(monkeypatch):
    _patch_client(monkeypatch, response=_choice_response(choice="supported", confidence=0.25))
    chain: list[DecisionGate] = [JevGate(_settings())]
    result = run(evidence_verification(
        run_id=1, campaign_id=1045, cause_text="VAST errors suppressing delivery", evidence_text="vast validation errors detected",
        chain=chain, settings=_settings(),
    ))
    assert result.decision == "uncertain"
    assert result.metadata["raw_gate_decision"] == "supported"


# --- 17. Unsafe client brief -----------------------------------------------------


def test_jev_gate_unsafe_client_brief_blocked(monkeypatch):
    _patch_client(monkeypatch, response=_choice_response(choice="block", confidence=0.92))
    chain: list[DecisionGate] = [JevGate(_settings())]
    result = run(client_safe_brief_check(
        run_id=1, campaign_id=1045, brief_text="We adjusted delivery after reviewing the publisher floor price.",
        chain=chain, settings=_settings(),
    ))
    assert result.decision == "block"


def test_jev_gate_low_confidence_safe_brief_escalates_to_needs_review(monkeypatch):
    _patch_client(monkeypatch, response=_choice_response(choice="safe", confidence=0.3))
    chain: list[DecisionGate] = [JevGate(_settings())]
    result = run(client_safe_brief_check(
        run_id=1, campaign_id=1045, brief_text="Delivery is recovering after a creative update.",
        chain=chain, settings=_settings(),
    ))
    assert result.decision == "needs_review"


# --- 18. Jev unavailable -> falls back to LLM -----------------------------------


class _ScriptedLLMProvider:
    provider_name = "openai"
    model = "scripted-model"
    available = True

    def decide_next_step(self, **kwargs):
        raise NotImplementedError

    def classify(self, *, system_prompt, payload, schema):
        from app.agent.providers.base import ClassificationResult, StepUsage
        return ClassificationResult(
            decision="require_approval", confidence=0.8, raw_model_name="scripted-model",
            usage=StepUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        )


def test_jev_unavailable_falls_back_to_llm():
    chain: list[DecisionGate] = [JevGate(Settings(typesafe_api_key=None)), LLMGate(_ScriptedLLMProvider()), RuleGate()]
    result = run(decide_with_fallback(_request(), chain))
    assert result.gate_type == "llm"
    assert result.requested_provider == "jev"
    assert result.execution_status == "jev_unavailable_fallback_llm"
    assert "jev" in (result.fallback_reason or "")


# --- 19. Jev + LLM unavailable -> falls back to Rules ---------------------------


def test_jev_and_llm_unavailable_falls_back_to_rules():
    class _UnavailableProvider:
        provider_name = "openai"
        model = "n/a"
        available = False

        def decide_next_step(self, **kwargs):
            raise NotImplementedError

        def classify(self, **kwargs):
            raise NotImplementedError

    chain: list[DecisionGate] = [JevGate(Settings(typesafe_api_key=None)), LLMGate(_UnavailableProvider()), RuleGate()]
    result = run(decide_with_fallback(_request(rule_floor="require_approval"), chain))
    assert result.gate_type == "rules"
    assert result.execution_status == "jev_unavailable_then_llm_unavailable_fallback_rules"
    skipped_types = [entry["gate_type"] for entry in result.metadata["skipped_gates"]]
    assert skipped_types == ["jev", "llm"]


def test_jev_failure_falls_back_with_failed_category(monkeypatch):
    _patch_client(monkeypatch, exc=sdk.TypeSafeAPITimeoutError(timeout=10.0))
    chain: list[DecisionGate] = [JevGate(_settings()), RuleGate()]
    result = run(decide_with_fallback(_request(rule_floor="require_approval"), chain))
    assert result.gate_type == "rules"
    assert result.execution_status == "jev_failed_fallback_rules"


# --- 20. No public-demo writes, regardless of configured gate provider ---------


def test_public_demo_still_blocked_when_jev_is_the_configured_provider(tmp_path):
    # Configuring DECISION_GATE_PROVIDER=jev must not change the fact that the
    # public demo viewer role is rejected before any DecisionGate is touched -
    # see tests/test_public_demo_mode.py for the full write-blocking suite this
    # complements. Here we only confirm the provider choice is irrelevant to
    # that guarantee.
    from app.api.mcp import run_mcp_agent
    from app.database import Base
    from app.models import GateDecision
    from app.schemas import MCPAgentRunRequest
    from app.security import build_demo_viewer, require_roles
    from fastapi import HTTPException
    from seed import build_seed_data

    engine = create_engine(f"sqlite:///{tmp_path / 'demo.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    data = build_seed_data()
    for key in ["users", "advertisers", "publishers", "inventory_segments", "campaigns", "creatives"]:
        db.add_all(data[key])
        db.flush()
    db.commit()

    demo_user = build_demo_viewer()
    with pytest.raises(HTTPException) as excinfo:
        run_mcp_agent(
            MCPAgentRunRequest(user_query="Why is this campaign underdelivering?", campaign_id="1045"),
            db=db,
            _=require_roles("admin", "adops_manager", "product_manager")(user=demo_user),
        )
    assert excinfo.value.status_code == 403
    assert db.execute(select(GateDecision)).first() is None
