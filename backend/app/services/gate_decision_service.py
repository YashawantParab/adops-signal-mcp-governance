"""Persistence for gate_decisions rows. Kept separate from mcp_governance_service
so the (already large) orchestration module doesn't also own DB-row shaping for
this concern.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.gates.base import DecisionResult
from app.models import GateDecision


def persist_gate_decision(
    db: Session,
    *,
    agent_run_id: int,
    campaign_id: int | None,
    decision_point: str,
    result: DecisionResult,
    rule_floor: str | None,
    final_decision: str,
    input_state: dict[str, Any] | None = None,
) -> GateDecision:
    row = GateDecision(
        agent_run_id=agent_run_id,
        campaign_id=campaign_id,
        decision_point=decision_point,
        gate_type=result.gate_type,
        provider=result.provider,
        model_name=result.model_name,
        decision=result.decision,
        probability=result.probability,
        confidence=result.confidence,
        rule_floor=rule_floor,
        final_decision=final_decision,
        latency_ms=result.latency_ms,
        estimated_cost_usd=result.cost_usd,
        input_reference=_hash_state(input_state) if input_state else None,
        metadata_json=result.metadata or None,
        schema_version=result.schema_version,
        requested_provider=result.requested_provider,
        fallback_reason=result.fallback_reason,
        execution_status=result.execution_status,
    )
    db.add(row)
    db.flush()
    return row


def _hash_state(state: dict[str, Any]) -> str:
    # A short reference, never the raw content - lets an auditor confirm what
    # was hashed if they still have the source (e.g. the diagnosis text stored
    # elsewhere) without this table itself carrying prompt-sized payloads.
    serialized = json.dumps(state, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
