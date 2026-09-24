"""The concrete decision-point functions that call the DecisionGate chain and
apply point-specific interpretation of the result. This is the only layer that
understands what a raw DecisionResult *means* for a given decision - the gates
themselves are generic.

Primary points (wired into the governed MCP agent run, app/services/mcp_governance_service.py):
  - risk_routing
  - evidence_verification
  - client_safe_brief_check

Secondary points (Phase 2D - implemented and testable, not yet wired into the
live agent loop; see docs/jev-integration-notes.md / CLAUDE.md for why):
  - tool_scope_check
  - prompt_injection_screen
  - risk_queue_triage
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.gates.base import DecisionGate, DecisionRequest, DecisionResult, apply_confidence_floor, apply_rule_floor

RISK_ROUTING_DECISIONS = ["auto_recommend", "require_approval", "block"]
EVIDENCE_VERIFICATION_DECISIONS = ["supported", "unsupported", "uncertain"]
CLIENT_SAFE_BRIEF_DECISIONS = ["safe", "needs_review", "block"]
TOOL_SCOPE_DECISIONS = ["in_scope", "out_of_scope", "uncertain"]
PROMPT_INJECTION_DECISIONS = ["normal_knowledge", "suspicious_instruction", "likely_prompt_injection"]
RISK_QUEUE_CATEGORIES = [
    "inventory_constraint", "creative_vast", "targeting_constraint", "frequency_cap",
    "bid_floor", "brand_safety", "publisher_supply", "approval_delay", "unknown",
]


@dataclass(frozen=True)
class GatedRiskRouting:
    final_routing: str
    rule_floor: str
    gate_result: DecisionResult


async def risk_routing(
    *, run_id: int, campaign_id: int, rule_floor: str, proposed_action: str,
    evidence_summary: dict[str, Any], chain: list[DecisionGate], settings: Settings,
) -> GatedRiskRouting:
    from app.gates import decide_with_fallback

    request = DecisionRequest(
        decision_point="risk_routing",
        run_id=run_id,
        campaign_id=campaign_id,
        state={"proposed_action": proposed_action, **evidence_summary},
        allowed_decisions=RISK_ROUTING_DECISIONS,
        rule_floor=rule_floor,
    )
    result = await decide_with_fallback(request, chain)
    final_routing = apply_rule_floor(
        rule_floor, result.decision, confidence=result.confidence, confidence_threshold=settings.gate_confidence_threshold
    )
    return GatedRiskRouting(final_routing=final_routing, rule_floor=rule_floor, gate_result=result)


async def evidence_verification(
    *, run_id: int, campaign_id: int, cause_text: str, evidence_text: str, chain: list[DecisionGate], settings: Settings,
) -> DecisionResult:
    from app.gates import decide_with_fallback

    request = DecisionRequest(
        decision_point="evidence_verification",
        run_id=run_id,
        campaign_id=campaign_id,
        state={"cause_text": cause_text, "evidence_text": evidence_text},
        allowed_decisions=EVIDENCE_VERIFICATION_DECISIONS,
    )
    result = await decide_with_fallback(request, chain)
    # Safety contract: a low-confidence "supported" (the permissive outcome - it
    # keeps the cause) must never pass through un-escalated. "unsupported" and
    # "uncertain" are already conservative outcomes on their own and are never
    # touched here.
    final_decision = apply_confidence_floor(
        result.decision, confidence=result.confidence, confidence_threshold=settings.gate_confidence_threshold,
        permissive_decision="supported", conservative_decision="uncertain",
    )
    if final_decision != result.decision:
        return dataclasses.replace(
            result, decision=final_decision, metadata={**result.metadata, "raw_gate_decision": result.decision, "escalated_reason": "low confidence"},
        )
    return result


async def client_safe_brief_check(
    *, run_id: int, campaign_id: int, brief_text: str, chain: list[DecisionGate], settings: Settings,
) -> DecisionResult:
    from app.gates import decide_with_fallback

    request = DecisionRequest(
        decision_point="client_safe_brief",
        run_id=run_id,
        campaign_id=campaign_id,
        state={"brief_text": brief_text},
        allowed_decisions=CLIENT_SAFE_BRIEF_DECISIONS,
    )
    result = await decide_with_fallback(request, chain)
    # Safety contract: a low-confidence "safe" (the permissive outcome - it
    # releases the brief to the client) must never pass through un-escalated.
    # "needs_review" and "block" are already conservative and never touched.
    final_decision = apply_confidence_floor(
        result.decision, confidence=result.confidence, confidence_threshold=settings.gate_confidence_threshold,
        permissive_decision="safe", conservative_decision="needs_review",
    )
    if final_decision != result.decision:
        return dataclasses.replace(
            result, decision=final_decision, metadata={**result.metadata, "raw_gate_decision": result.decision, "escalated_reason": "low confidence"},
        )
    return result


async def tool_scope_check(
    *, run_id: int, campaign_id: int, tool_name: str, tool_campaign_id: int | None,
    scoped_campaign_id: int, chain: list[DecisionGate],
) -> DecisionResult:
    """Advisory only - see module docstring. Never used to grant access RBAC/the
    deterministic scope check in governance_wrapper would deny, and not
    currently wired to block anything on its own."""
    from app.gates import decide_with_fallback

    request = DecisionRequest(
        decision_point="tool_scope",
        run_id=run_id,
        campaign_id=campaign_id,
        state={"tool_name": tool_name, "campaign_id": tool_campaign_id, "scoped_campaign_id": scoped_campaign_id},
        allowed_decisions=TOOL_SCOPE_DECISIONS,
    )
    return await decide_with_fallback(request, chain)


async def prompt_injection_screen(
    *, run_id: int, campaign_id: int | None, retrieved_text: str, source: str, chain: list[DecisionGate],
) -> DecisionResult:
    from app.gates import decide_with_fallback

    request = DecisionRequest(
        decision_point="prompt_injection_screen",
        run_id=run_id,
        campaign_id=campaign_id,
        state={"retrieved_text": retrieved_text, "source": source},
        allowed_decisions=PROMPT_INJECTION_DECISIONS,
    )
    return await decide_with_fallback(request, chain)


async def risk_queue_triage(
    *, run_id: int, campaign_id: int, signals: dict[str, Any], chain: list[DecisionGate],
) -> DecisionResult:
    from app.gates import decide_with_fallback

    request = DecisionRequest(
        decision_point="risk_queue_triage",
        run_id=run_id,
        campaign_id=campaign_id,
        state=signals,
        allowed_decisions=RISK_QUEUE_CATEGORIES,
    )
    return await decide_with_fallback(request, chain)
