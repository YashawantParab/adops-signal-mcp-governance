"""The provider-neutral DecisionGate abstraction (Phase 2).

    LLM/MCP agent -> evidence -> proposed diagnosis/action
        -> DecisionGate (JevGate | LLMGate | RuleGate)
        -> deterministic rule floor (can only be escalated, never downgraded)
        -> human approval / block

No vendor SDK object (a TypeSafe SystemOneResponse, an OpenAI/Anthropic response) may
leak past a concrete DecisionGate implementation - every gate returns only the plain
DecisionResult dataclass defined here.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = "gate-decision-v1"

DecisionPoint = Literal[
    "risk_routing",
    "evidence_verification",
    "client_safe_brief",
    "tool_scope",
    "prompt_injection_screen",
    "risk_queue_triage",
]

GateType = Literal["jev", "llm", "rules"]

# risk_routing's three-value output, ordered from least to most restrictive. The
# deterministic rule floor may only be escalated (moved right), never downgraded
# (moved left) by a probabilistic gate - see apply_rule_floor below.
RiskRoutingDecision = Literal["auto_recommend", "require_approval", "block"]
_ROUTING_ORDER: dict[str, int] = {"auto_recommend": 0, "require_approval": 1, "block": 2}


@dataclass(frozen=True)
class DecisionRequest:
    decision_point: DecisionPoint
    run_id: int
    campaign_id: int | None
    state: dict[str, Any]
    allowed_decisions: list[str]
    rule_floor: str | None = None


@dataclass(frozen=True)
class DecisionResult:
    decision: str
    gate_type: GateType
    latency_ms: int
    probability: float | None = None
    confidence: float | None = None
    provider: str | None = None
    model_name: str | None = None
    cost_usd: float | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION


class GateUnavailable(RuntimeError):
    """Raised by a gate that cannot answer right now (no credentials, provider
    down, malformed response). Callers (the gate chain / decision-point
    functions) catch this and fall through to the next configured gate -
    never silently pretend an unavailable gate ran."""


class DecisionGate(ABC):
    gate_type: GateType

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether this gate can currently answer (has credentials/config)."""

    @abstractmethod
    async def decide(self, request: DecisionRequest) -> DecisionResult:
        """Raises GateUnavailable if this gate cannot answer this request."""
        raise NotImplementedError


def apply_rule_floor(
    rule_floor: RiskRoutingDecision,
    gate_decision: RiskRoutingDecision,
    *,
    confidence: float | None,
    confidence_threshold: float,
) -> RiskRoutingDecision:
    """The non-negotiable rule: a probabilistic gate may escalate risk routing,
    never downgrade it below the deterministic rule floor. A gate decision
    below the confidence threshold is treated as require_approval at minimum,
    regardless of what it decided - low confidence must never resolve to
    auto_recommend."""
    effective_gate_decision = gate_decision
    if confidence is not None and confidence < confidence_threshold:
        if _ROUTING_ORDER[gate_decision] < _ROUTING_ORDER["require_approval"]:
            effective_gate_decision = "require_approval"
    return max(rule_floor, effective_gate_decision, key=lambda value: _ROUTING_ORDER[value])
