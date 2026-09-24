from __future__ import annotations

import logging

from app.agent.providers import get_llm_provider
from app.config import Settings, get_settings
from app.gates.base import (
    DecisionGate,
    DecisionRequest,
    DecisionResult,
    GateUnavailable,
)
from app.gates.jev_gate import JevGate
from app.gates.llm_gate import LLMGate
from app.gates.rule_gate import RuleGate

__all__ = [
    "DecisionGate",
    "DecisionRequest",
    "DecisionResult",
    "GateUnavailable",
    "JevGate",
    "LLMGate",
    "RuleGate",
    "get_decision_gate_chain",
    "decide_with_fallback",
]

logger = logging.getLogger(__name__)

# Explicit, documented fallback order: the configured primary provider first,
# then progressively simpler/more-available gates, ending at RuleGate, which
# is always available and is the ultimate backstop (Phase 2B requirement).
_CHAIN_ORDER: dict[str, list[str]] = {
    "jev": ["jev", "llm", "rules"],
    "llm": ["llm", "rules"],
    "rules": ["rules"],
}


def get_decision_gate_chain(settings: Settings | None = None) -> list[DecisionGate]:
    settings = settings or get_settings()
    order = _CHAIN_ORDER.get(settings.decision_gate_provider, ["rules"])
    provider = get_llm_provider(settings)
    gates: dict[str, DecisionGate] = {
        "jev": JevGate(settings),
        "llm": LLMGate(provider),
        "rules": RuleGate(),
    }
    return [gates[name] for name in order]


async def decide_with_fallback(request: DecisionRequest, chain: list[DecisionGate]) -> DecisionResult:
    """Try each gate in the configured chain in order; the first one that
    answers wins. RuleGate is always available and always last, so this never
    raises - it always returns a real DecisionResult, with `metadata`
    recording which gates were skipped and why, and `requested_provider` /
    `fallback_reason` / `execution_status` set so an observer never has to
    infer what happened from latency/reason alone (never silently pretends an
    unavailable/failed gate ran)."""
    requested_provider = chain[0].gate_type if chain else None
    skipped: list[dict[str, str]] = []
    for gate in chain:
        try:
            result = await gate.decide(request)
        except GateUnavailable as exc:
            logger.info("Gate %s unavailable for %s: %s", gate.gate_type, request.decision_point, exc)
            skipped.append({"gate_type": gate.gate_type, "reason": str(exc), "error_category": exc.error_category})
            continue
        if skipped:
            fallback_reason = "; ".join(f"{entry['gate_type']}: {entry['reason']}" for entry in skipped)
            execution_status = "_then_".join(f"{entry['gate_type']}_{entry['error_category']}" for entry in skipped)
            execution_status = f"{execution_status}_fallback_{result.gate_type}"
            result = DecisionResult(
                decision=result.decision,
                gate_type=result.gate_type,
                latency_ms=result.latency_ms,
                probability=result.probability,
                confidence=result.confidence,
                provider=result.provider,
                model_name=result.model_name,
                cost_usd=result.cost_usd,
                reason=result.reason,
                metadata={**result.metadata, "skipped_gates": skipped},
                schema_version=result.schema_version,
                requested_provider=requested_provider,
                fallback_reason=fallback_reason,
                execution_status=execution_status,
            )
        else:
            result = DecisionResult(
                decision=result.decision,
                gate_type=result.gate_type,
                latency_ms=result.latency_ms,
                probability=result.probability,
                confidence=result.confidence,
                provider=result.provider,
                model_name=result.model_name,
                cost_usd=result.cost_usd,
                reason=result.reason,
                metadata=result.metadata,
                schema_version=result.schema_version,
                requested_provider=requested_provider,
                fallback_reason=None,
                execution_status=f"{result.gate_type}_executed",
            )
        return result
    raise AssertionError("RuleGate is always available - the chain must never be exhausted")
