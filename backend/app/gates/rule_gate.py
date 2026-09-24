"""RuleGate: the deterministic, always-available decision gate. No network call,
no external dependency, no confidence uncertainty beyond what it explicitly says.
This is both a real DecisionGate implementation (selectable via
DECISION_GATE_PROVIDER=rules) and the unconditional fallback every other gate
degrades to.
"""
from __future__ import annotations

import re
import time
from typing import Any

from app.gates.base import DecisionGate, DecisionRequest, DecisionResult

# Client-safe briefs must never leak these internal-only terms or patterns. Kept
# deliberately conservative (few false positives) rather than exhaustive - this
# is a floor, not the only line of defense (LLMGate/JevGate can also flag).
FORBIDDEN_CLIENT_SAFE_TERMS = [
    "publisher floor",
    "floor price",
    "loss reason",
    "already fixed",
    "already applied",
    "vast_validation",
    "sql_analysis_tool",
    "campaign_id",
    "evidence_id",
    "agent_run",
    "mcp_tool_call",
    "tool_name",
    "database",
    "sqlalchemy",
    "stack trace",
    "traceback",
]
_INTERNAL_ID_PATTERN = re.compile(r"\bE\d{1,4}\b")  # evidence-ID-shaped tokens like "E12"

# Coarse keyword-overlap thresholds for the evidence-verification heuristic. Not a
# semantic check - a cheap deterministic sanity signal only. See EvidenceVerification
# docstring below for why this stays conservative.
_SUPPORTED_OVERLAP = 0.15


class RuleGate(DecisionGate):
    gate_type = "rules"

    @property
    def available(self) -> bool:
        return True  # the deterministic gate is always available

    async def decide(self, request: DecisionRequest) -> DecisionResult:
        started = time.perf_counter()
        if request.decision_point == "risk_routing":
            decision, confidence, reason = self._risk_routing(request)
        elif request.decision_point == "evidence_verification":
            decision, confidence, reason = self._evidence_verification(request)
        elif request.decision_point == "client_safe_brief":
            decision, confidence, reason = self._client_safe_brief(request)
        elif request.decision_point == "tool_scope":
            decision, confidence, reason = self._tool_scope(request)
        elif request.decision_point == "prompt_injection_screen":
            decision, confidence, reason = self._prompt_injection_screen(request)
        elif request.decision_point == "risk_queue_triage":
            decision, confidence, reason = self._risk_queue_triage(request)
        else:
            decision, confidence, reason = request.allowed_decisions[0], 0.5, "unrecognized decision point"

        latency_ms = max(int((time.perf_counter() - started) * 1000), 0)
        return DecisionResult(
            decision=decision,
            gate_type="rules",
            latency_ms=latency_ms,
            confidence=confidence,
            probability=confidence,
            reason=reason,
        )

    @staticmethod
    def _risk_routing(request: DecisionRequest) -> tuple[str, float, str]:
        # RuleGate IS the rule floor - it has nothing additional to escalate on,
        # so it returns the floor itself with full confidence. This makes
        # DECISION_GATE_PROVIDER=rules a true no-op on top of the existing risk
        # engine, by construction.
        floor = request.rule_floor or "auto_recommend"
        return floor, 1.0, f"deterministic rule floor is {floor}"

    @staticmethod
    def _evidence_verification(request: DecisionRequest) -> tuple[str, float, str]:
        """Coarse keyword-overlap sanity check between a claimed root cause and
        the evidence payload it cites. This is NOT semantic verification - it
        cannot catch a claim that misreads real evidence, only a claim whose
        wording shares essentially nothing with what was actually retrieved.
        It supplements, and never replaces, the deterministic evidence-ID
        existence/scope check already enforced in mcp_agent_runtime.py."""
        cause_text = str(request.state.get("cause_text", ""))
        evidence_text = str(request.state.get("evidence_text", ""))
        cause_tokens = _tokenize(cause_text)
        evidence_tokens = set(_tokenize(evidence_text))
        if not cause_tokens:
            return "uncertain", 0.3, "no cause text to check"
        overlap = sum(1 for token in cause_tokens if token in evidence_tokens) / len(cause_tokens)
        if overlap >= _SUPPORTED_OVERLAP:
            return "supported", min(0.6 + overlap, 0.95), f"keyword overlap {overlap:.2f}"
        if overlap > 0:
            return "uncertain", 0.5, f"low keyword overlap {overlap:.2f}"
        return "unsupported", 0.7, "no keyword overlap between claim and cited evidence"

    @staticmethod
    def _client_safe_brief(request: DecisionRequest) -> tuple[str, float, str]:
        text = str(request.state.get("brief_text", ""))
        lowered = text.lower()
        violations = [term for term in FORBIDDEN_CLIENT_SAFE_TERMS if term in lowered]
        if _INTERNAL_ID_PATTERN.search(text):
            violations.append("evidence-id-shaped token")
        if violations:
            return "block", 0.9, f"forbidden terms/patterns: {', '.join(violations)}"
        return "safe", 0.85, "no forbidden internal terms detected"

    @staticmethod
    def _tool_scope(request: DecisionRequest) -> tuple[str, float, str]:
        # RBAC/permission itself is deterministic and enforced elsewhere
        # (governance_wrapper); this only judges topical relevance.
        tool_name = str(request.state.get("tool_name", ""))
        campaign_id = request.state.get("campaign_id")
        scoped_campaign_id = request.state.get("scoped_campaign_id")
        if campaign_id is not None and scoped_campaign_id is not None and campaign_id != scoped_campaign_id:
            return "out_of_scope", 0.95, "tool argument targets a different campaign"
        return "in_scope", 0.8, "tool call targets the investigation's own campaign"

    @staticmethod
    def _prompt_injection_screen(request: DecisionRequest) -> tuple[str, float, str]:
        text = str(request.state.get("retrieved_text", "")).lower()
        suspicious_markers = [
            "ignore previous instructions",
            "ignore all previous",
            "disregard the above",
            "you are now",
            "system prompt",
            "act as",
            "override your instructions",
            "do not follow the",
        ]
        hits = [marker for marker in suspicious_markers if marker in text]
        if hits:
            return "likely_prompt_injection", 0.85, f"matched: {', '.join(hits)}"
        return "normal_knowledge", 0.7, "no injection markers matched"

    @staticmethod
    def _risk_queue_triage(request: DecisionRequest) -> tuple[str, float, str]:
        signals = request.state
        if signals.get("rejected_creative_count", 0) or signals.get("vast_error_count", 0):
            return "creative_vast", 0.75, "creative rejection or VAST errors present"
        if signals.get("below_floor_rate", 0) and signals["below_floor_rate"] > 45:
            return "bid_floor", 0.7, "high below-floor bid rate"
        if signals.get("eligible_inventory_percentage") is not None and signals["eligible_inventory_percentage"] < 25:
            return "targeting_constraint", 0.7, "narrow eligible inventory"
        if signals.get("frequency_cap") is not None and signals["frequency_cap"] <= 1:
            return "frequency_cap", 0.65, "restrictive frequency cap"
        if signals.get("brand_safety_finding_count", 0):
            return "brand_safety", 0.6, "brand-safety findings present"
        return "unknown", 0.4, "no dominant deterministic signal"


def _tokenize(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2]
