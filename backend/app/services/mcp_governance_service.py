from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from app.agent.mcp_agent_runtime import AgentRunOutcome, AgentTerminated, run_governed_mcp_agent
from app.agent.providers import LLMProvider, get_llm_provider
from app.config import Settings, get_settings
from app.gates import get_decision_gate_chain
from app.gates.decision_points import client_safe_brief_check, evidence_verification, risk_routing
from app.services.gate_decision_service import persist_gate_decision
from app.models import (
    AgentRun,
    ApprovalRequest,
    BlockedAction,
    Campaign,
    Creative,
    MCPToolCall,
    PacingSnapshot,
    PolicyCheck,
    RunFeedback,
    User,
    VastValidationError,
)
from app.schemas import (
    AgentRunDetail,
    AgentRunRead,
    ApprovalRequestRead,
    BlockedActionRead,
    CampaignHealth,
    GateDecisionRead,
    MCPAgentRunResponse,
    MCPSummary,
    MCPToolRead,
    MCPToolCallRead,
    MCPToolTimelineEntry,
    PolicyCheckRead,
    RunFeedbackRead,
)
from app.services.campaign_service import get_campaign_health as compute_campaign_health, get_campaign_or_none
from app.services.json_fields import parse_list
from app.services.mcp_tool_registry import MCP_TOOL_DESCRIPTORS
from app.services.recommendation_service import list_recommendations
from app.services.vast_service import suggested_fix_for_errors
from app.time_utils import utc_now

logger = logging.getLogger(__name__)


class ApprovalRequestAlreadyDecidedError(ValueError):
    pass


class InvalidCampaignIdError(ValueError):
    pass


class CampaignNotFoundError(ValueError):
    pass


class AgentRunNotFoundError(ValueError):
    pass


def _feedback_to_read(feedback: RunFeedback) -> RunFeedbackRead:
    return RunFeedbackRead(
        id=feedback.id,
        agent_run_id=feedback.agent_run_id,
        user_id=feedback.user_id,
        reviewer_name=feedback.user.full_name if feedback.user else None,
        rating=feedback.rating,
        comment=feedback.comment,
        created_at=feedback.created_at,
    )


def submit_run_feedback(db: Session, run_id: int, *, user: User, rating: str, comment: str | None) -> RunFeedbackRead:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise AgentRunNotFoundError(f"Agent run {run_id} was not found")
    feedback = RunFeedback(agent_run_id=run_id, user_id=user.id, rating=rating, comment=comment)
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    feedback.user = user
    return _feedback_to_read(feedback)


def _approval_to_read(approval: ApprovalRequest) -> ApprovalRequestRead:
    return ApprovalRequestRead(
        id=approval.id,
        agent_run_id=approval.agent_run_id,
        campaign_id=approval.campaign_id,
        campaign_name=approval.campaign.campaign_name if approval.campaign else None,
        proposed_action=approval.proposed_action,
        risk_score=approval.risk_score,
        risk_level=approval.risk_level,
        rationale=approval.rationale,
        status=approval.status,
        reviewer_id=approval.reviewer_id,
        reviewer_name=approval.reviewer.full_name if approval.reviewer else None,
        reviewed_at=approval.reviewed_at,
        created_at=approval.created_at,
    )


def _agent_run_to_read(run: AgentRun) -> AgentRunRead:
    return AgentRunRead(
        id=run.id,
        user_query=run.user_query,
        campaign_id=run.campaign_id,
        campaign_name=run.campaign.campaign_name if run.campaign else None,
        status=run.status,
        risk_level=run.risk_level,
        risk_score=run.risk_score,
        final_recommendation=run.final_recommendation,
        approval_required=run.approval_required,
        created_at=run.created_at,
        completed_at=run.completed_at,
        execution_mode=run.execution_mode,
        llm_provider=run.llm_provider,
        model_name=run.model_name,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        total_tokens=run.total_tokens,
        estimated_cost_usd=run.estimated_cost_usd,
        steps_used=run.steps_used,
        max_steps=run.max_steps,
        fallback_reason=run.fallback_reason,
        client_safe_brief=run.client_safe_brief,
        client_safe_brief_status=run.client_safe_brief_status,
    )


def _agent_run_to_detail(run: AgentRun) -> AgentRunDetail:
    base = _agent_run_to_read(run).model_dump()
    return AgentRunDetail(
        **base,
        tool_calls=[MCPToolCallRead.model_validate(item) for item in run.tool_calls],
        approval_requests=[_approval_to_read(item) for item in run.approval_requests],
        policy_checks=[PolicyCheckRead.model_validate(item) for item in run.policy_checks],
        blocked_actions=[BlockedActionRead.model_validate(item) for item in run.blocked_actions],
        gate_decisions=[GateDecisionRead.model_validate(item) for item in run.gate_decisions],
        feedback=[_feedback_to_read(item) for item in run.feedback],
    )


def list_agent_runs(db: Session) -> list[AgentRunRead]:
    runs = list(
        db.execute(
            select(AgentRun)
            .options(selectinload(AgentRun.campaign))
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(100)
        ).scalars()
    )
    return [_agent_run_to_read(run) for run in runs]


def get_agent_run_detail(db: Session, run_id: int) -> AgentRunDetail | None:
    run = db.execute(
        select(AgentRun)
        .where(AgentRun.id == run_id)
        .options(
            selectinload(AgentRun.campaign),
            selectinload(AgentRun.tool_calls),
            selectinload(AgentRun.policy_checks),
            selectinload(AgentRun.blocked_actions),
            selectinload(AgentRun.gate_decisions),
            selectinload(AgentRun.feedback).selectinload(RunFeedback.user),
            selectinload(AgentRun.approval_requests).selectinload(ApprovalRequest.campaign),
            selectinload(AgentRun.approval_requests).selectinload(ApprovalRequest.reviewer),
        )
    ).scalar_one_or_none()
    if not run:
        return None

    run.tool_calls.sort(key=lambda item: item.created_at)
    run.policy_checks.sort(key=lambda item: item.created_at)
    run.blocked_actions.sort(key=lambda item: item.created_at)
    run.approval_requests.sort(key=lambda item: item.created_at)
    run.gate_decisions.sort(key=lambda item: item.created_at)
    run.feedback.sort(key=lambda item: item.created_at)
    return _agent_run_to_detail(run)


def list_approval_requests(db: Session) -> list[ApprovalRequestRead]:
    approvals = list(
        db.execute(
            select(ApprovalRequest)
            .options(selectinload(ApprovalRequest.campaign), selectinload(ApprovalRequest.reviewer))
            .order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc())
            .limit(100)
        ).scalars()
    )
    return [_approval_to_read(approval) for approval in approvals]


def decide_approval_request(
    db: Session,
    approval_id: int,
    status: str,
    *,
    reviewer: User,
    rationale: str,
) -> ApprovalRequest | None:
    approval = db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.id == approval_id)
        .options(selectinload(ApprovalRequest.campaign), selectinload(ApprovalRequest.reviewer))
    ).scalar_one_or_none()
    if not approval:
        return None
    if approval.status != "pending":
        raise ApprovalRequestAlreadyDecidedError(f"Approval request {approval_id} is already {approval.status}")

    approval.status = status
    approval.reviewer_id = reviewer.id
    approval.reviewer = reviewer
    approval.reviewed_at = utc_now()
    approval.rationale = rationale.strip()
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval


def mcp_tool_registry(db: Session) -> list[MCPToolRead]:
    rows = db.execute(
        select(
            MCPToolCall.tool_name,
            func.count(MCPToolCall.id),
            func.sum(case((MCPToolCall.status != "success", 1), else_=0)),
            func.max(MCPToolCall.created_at),
        ).group_by(MCPToolCall.tool_name)
    ).all()
    stats = {
        tool_name: {
            "call_count": int(call_count),
            "failure_rate": round((int(failures) / int(call_count)) * 100, 1) if call_count else 0.0,
            "last_used_at": last_used_at,
        }
        for tool_name, call_count, failures, last_used_at in rows
    }
    return [
        descriptor.model_copy(
            update=stats.get(descriptor.name, {"call_count": 0, "failure_rate": 0.0, "last_used_at": None})
        )
        for descriptor in MCP_TOOL_DESCRIPTORS
    ]


def mcp_summary(db: Session) -> MCPSummary:
    total_runs = db.scalar(select(func.count(AgentRun.id))) or 0
    completed_runs = db.scalar(select(func.count(AgentRun.id)).where(AgentRun.status == "completed")) or 0
    failed_runs = db.scalar(select(func.count(AgentRun.id)).where(AgentRun.status == "failed")) or 0
    average_risk_score = db.scalar(select(func.avg(AgentRun.risk_score))) or 0
    tool_calls = db.scalar(select(func.count(MCPToolCall.id))) or 0
    average_tool_latency_ms = db.scalar(select(func.avg(MCPToolCall.latency_ms))) or 0
    blocked_actions = db.scalar(select(func.count(BlockedAction.id))) or 0

    approval_rows = db.execute(select(ApprovalRequest.status, func.count(ApprovalRequest.id)).group_by(ApprovalRequest.status))
    policy_rows = db.execute(select(PolicyCheck.result, func.count(PolicyCheck.id)).group_by(PolicyCheck.result))

    return MCPSummary(
        total_runs=int(total_runs),
        completed_runs=int(completed_runs),
        failed_runs=int(failed_runs),
        approval_requests={status: int(count) for status, count in approval_rows},
        blocked_actions=int(blocked_actions),
        policy_checks={status: int(count) for status, count in policy_rows},
        average_risk_score=round(float(average_risk_score), 2),
        tool_calls=int(tool_calls),
        average_tool_latency_ms=round(float(average_tool_latency_ms), 1),
    )


# --- Deterministic agent-run orchestration -----------------------------------
#
# POST /api/mcp/agent/run composes the same read-only signals already exposed
# as MCP tools (campaign health, pacing, VAST validation, brand safety,
# policy search) into a single governed run. It never mutates campaign,
# budget, or pacing data - it only ever writes governance/audit rows
# (agent_runs, mcp_tool_calls, approval_requests, blocked_actions,
# policy_checks), same as the rest of this module.

REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_DIR = REPO_ROOT / "docs" / "policies"
BRAND_SENSITIVE_CATEGORIES = {"Finance", "Business News", "News", "Gaming"}
POLICY_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "in", "is", "of", "on", "or", "the", "to", "with",
}

# Score contributions are additive and capped at 100; thresholds below decide
# the resulting LOW/MEDIUM/HIGH/CRITICAL band. A rejected creative always
# forces CRITICAL (it must not serve, matching brand-safety-policy.md), even
# if the additive score alone would land lower.
_PACING_RISK_WEIGHT = {"High": 45, "Medium": 25, "Low": 8, "Unknown": 15}
_FINDING_SEVERITY_WEIGHT = {"high": 15, "medium": 8, "low": 3}


def _parse_campaign_id(raw: str) -> int | None:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _tokenize(value: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in POLICY_STOP_WORDS
    ]


def _policy_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _timed(fn):
    started = time.perf_counter()
    result = fn()
    latency_ms = max(int((time.perf_counter() - started) * 1000), 1)
    return result, latency_ms


def _pacing_snapshot_summary(db: Session, campaign: Campaign) -> dict[str, Any]:
    snapshots = list(
        db.execute(
            select(PacingSnapshot)
            .where(PacingSnapshot.campaign_id == campaign.id)
            .order_by(PacingSnapshot.snapshot_date)
        ).scalars()
    )
    if not snapshots:
        return {"found": False, "pacing_percentage": None, "risk_level": None, "delta_percentage_points": None, "snapshot_count": 0}
    latest = snapshots[-1]
    prior = snapshots[-2] if len(snapshots) > 1 else None
    delta = round(latest.pacing_percentage - prior.pacing_percentage, 1) if prior else None
    return {
        "found": True,
        "pacing_percentage": round(latest.pacing_percentage, 1),
        "risk_level": latest.risk_level,
        "delta_percentage_points": delta,
        "snapshot_count": len(snapshots),
    }


def _vast_validation_summary(db: Session, campaign: Campaign) -> dict[str, Any]:
    creatives = list(db.execute(select(Creative).where(Creative.campaign_id == campaign.id)).scalars())
    errors = list(
        db.execute(
            select(VastValidationError)
            .join(Creative, Creative.id == VastValidationError.creative_id)
            .where(Creative.campaign_id == campaign.id)
        ).scalars()
    )
    rejected = [creative for creative in creatives if creative.approval_status == "rejected"]
    return {
        "creative_count": len(creatives),
        "rejected_count": len(rejected),
        "vast_error_count": len(errors),
        "valid": not rejected and not errors,
        "suggested_fix": suggested_fix_for_errors(errors, "rejected" if rejected else "approved"),
    }


def _brand_safety_findings(db: Session, campaign: Campaign) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    categories = parse_list(campaign.target_content_categories)
    sensitive_categories = sorted(set(categories) & BRAND_SENSITIVE_CATEGORIES)
    if sensitive_categories:
        findings.append(
            {
                "type": "sensitive_content_category",
                "severity": "medium",
                "message": "Campaign targets content categories that require brand-suitability review.",
                "evidence": {"target_content_categories": sensitive_categories},
            }
        )

    if campaign.advertiser and campaign.advertiser.industry in {"Finance", "Gaming"}:
        findings.append(
            {
                "type": "regulated_or_sensitive_advertiser_vertical",
                "severity": "medium",
                "message": "Advertiser industry requires conservative placement and claims review controls.",
                "evidence": {"advertiser_name": campaign.advertiser.name, "industry": campaign.advertiser.industry},
            }
        )

    rejected_count = db.scalar(
        select(func.count(Creative.id)).where(
            Creative.campaign_id == campaign.id, Creative.approval_status == "rejected"
        )
    ) or 0
    if rejected_count:
        findings.append(
            {
                "type": "creative_approval_block",
                "severity": "high",
                "message": "Rejected creative must not serve until corrected and revalidated.",
                "evidence": {"rejected_creative_count": int(rejected_count)},
            }
        )

    vast_error_count = db.scalar(
        select(func.count(VastValidationError.id))
        .join(Creative, Creative.id == VastValidationError.creative_id)
        .where(Creative.campaign_id == campaign.id)
    ) or 0
    if vast_error_count:
        findings.append(
            {
                "type": "creative_quality_governance",
                "severity": "medium",
                "message": "Persisted VAST errors should be reviewed before scaling delivery.",
                "evidence": {"vast_error_count": int(vast_error_count)},
            }
        )

    return {"findings": findings, "finding_count": len(findings)}


def _search_policy_context(query: str) -> dict[str, Any]:
    tokens = set(_tokenize(query))
    if not tokens or not POLICY_DIR.exists():
        return {"matches": []}

    matches: list[dict[str, Any]] = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        content_tokens = _tokenize(content)
        score = sum(1 for token in content_tokens if token in tokens)
        title = _policy_title(content, path.stem)
        title_score = sum(3 for token in tokens if token in title.lower())
        total_score = score + title_score
        if total_score <= 0:
            continue
        matches.append(
            {
                "source": str(path.relative_to(REPO_ROOT)),
                "title": title,
                "score": total_score,
                "matched_keywords": sorted(token for token in tokens if token in content.lower()),
            }
        )

    matches.sort(key=lambda item: (-item["score"], item["source"]))
    return {"matches": matches[:5]}


def _score_risk(health: CampaignHealth, vast_result: dict[str, Any], brand_result: dict[str, Any]) -> tuple[float, str]:
    score = _PACING_RISK_WEIGHT.get(health.risk_level, 15)
    if vast_result["rejected_count"] > 0:
        score += 25
    score += min(vast_result["vast_error_count"] * 3, 15)
    score += sum(_FINDING_SEVERITY_WEIGHT.get(finding["severity"], 0) for finding in brand_result["findings"])
    score = min(round(float(score), 1), 100.0)

    has_high_finding = any(finding["severity"] == "high" for finding in brand_result["findings"])
    if score >= 85 or (vast_result["rejected_count"] > 0 and has_high_finding):
        level = "CRITICAL"
    elif score >= 60:
        level = "HIGH"
    elif score >= 35:
        level = "MEDIUM"
    else:
        level = "LOW"
    return score, level


def _derive_proposed_action(db: Session, campaign: Campaign, health: CampaignHealth) -> str:
    pending = [item for item in list_recommendations(db, campaign.id) if item.status == "pending"]
    if pending:
        top = pending[0]
        return f"{top.title}: {top.description}"
    if health.main_suspected_issue == "Healthy":
        return "Continue monitoring campaign pacing and creative approval status; no corrective action needed."
    return (
        f"Address root cause ({health.main_suspected_issue}) through creative, inventory, "
        "or pacing review before any spend change."
    )


def _build_rationale(
    health: CampaignHealth,
    vast_result: dict[str, Any],
    brand_result: dict[str, Any],
    policy_result: dict[str, Any],
) -> str:
    parts = [f"Pacing risk is {health.risk_level.lower()} at {health.pacing_percentage}%."]
    if vast_result["rejected_count"]:
        parts.append(f"{vast_result['rejected_count']} rejected creative(s) block delivery.")
    if vast_result["vast_error_count"]:
        parts.append(f"{vast_result['vast_error_count']} persisted VAST error(s) require review.")
    if brand_result["finding_count"]:
        parts.append(f"{brand_result['finding_count']} brand-safety finding(s) identified.")
    if policy_result["matches"]:
        parts.append(f"Relevant policy: {policy_result['matches'][0]['title']}.")
    return " ".join(parts)


def run_agent_orchestration(db: Session, user_query: str, campaign_id_raw: str) -> MCPAgentRunResponse:
    """Public entrypoint for POST /api/mcp/agent/run.

    Dispatches to the real governed LLM + MCP agent when a provider is
    configured and the feature is enabled; degrades to the deterministic
    orchestration on any failure, with an honest, persisted fallback_reason.
    Never silently pretends the LLM/MCP path ran when it did not.
    """
    campaign_id = _parse_campaign_id(campaign_id_raw)
    if campaign_id is None:
        raise InvalidCampaignIdError(f"campaign_id must be a positive integer, received {campaign_id_raw!r}")

    campaign = get_campaign_or_none(db, campaign_id)
    if campaign is None:
        raise CampaignNotFoundError(f"Campaign {campaign_id} was not found")

    settings = get_settings()
    if not settings.mcp_agent_enabled:
        return run_deterministic_fallback_orchestration(db, campaign, user_query, fallback_reason="mcp_agent_disabled")

    provider = get_llm_provider(settings)
    try:
        return asyncio.run(_run_llm_mcp_agent_orchestration(db, campaign, user_query, provider, settings))
    except AgentTerminated as exc:
        db.rollback()
        logger.info("Governed MCP agent fell back to deterministic orchestration: %s", exc.reason_code)
        return run_deterministic_fallback_orchestration(db, campaign, user_query, fallback_reason=exc.reason_code)
    except Exception:  # defensive boundary: an unexpected agent bug must never break the demo
        db.rollback()
        logger.exception("Unexpected governed MCP agent failure; falling back to deterministic orchestration")
        return run_deterministic_fallback_orchestration(db, campaign, user_query, fallback_reason="unexpected_agent_error")


async def _run_llm_mcp_agent_orchestration(
    db: Session, campaign: Campaign, user_query: str, provider: LLMProvider, settings: Settings
) -> MCPAgentRunResponse:
    campaign_id = campaign.id
    run = AgentRun(
        user_query=user_query.strip(),
        campaign_id=campaign_id,
        status="running",
        risk_level="LOW",
        risk_score=0.0,
        final_recommendation="",
        approval_required=False,
        execution_mode="llm_mcp_agent",
        max_steps=settings.max_agent_steps,
    )
    db.add(run)
    db.flush()

    outcome = await run_governed_mcp_agent(
        db,
        agent_run_id=run.id,
        campaign_id=campaign_id,
        user_query=user_query,
        provider=provider,
        settings=settings,
    )

    gate_chain = get_decision_gate_chain(settings)

    # Evidence-verification gate: supplements (never replaces) the deterministic
    # evidence-ID existence/scope check already enforced in mcp_agent_runtime.py.
    # "unsupported" (zero keyword overlap under RuleGate, or an explicit
    # unsupported call from LLM/JevGate) removes a cause outright. "uncertain"
    # is persisted for audit but not removed - a coarse gate's uncertainty is
    # not itself grounds to discard an already evidence-ID-verified cause.
    verified_causes = []
    for index, cause in enumerate(outcome.grounded_root_causes):
        evidence_text = " ".join(
            str(outcome.evidence_ledger[evidence_id].data) for evidence_id in cause.evidence_ids if evidence_id in outcome.evidence_ledger
        )
        cause_text = f"{cause.cause}. {cause.recommendation_description}"
        verification = await evidence_verification(
            run_id=run.id, campaign_id=campaign_id, cause_text=cause_text, evidence_text=evidence_text, chain=gate_chain,
        )
        persist_gate_decision(
            db, agent_run_id=run.id, campaign_id=campaign_id, decision_point="evidence_verification",
            result=verification, rule_floor=None, final_decision=verification.decision,
            input_state={"cause_index": index, "cause": cause.cause, "evidence_ids": cause.evidence_ids},
        )
        if verification.decision != "unsupported":
            verified_causes.append(cause)

    if not verified_causes:
        raise AgentTerminated(
            "no_gate_supported_causes",
            "Every grounded root cause was classified unsupported by the evidence-verification gate",
        )

    # Rule floor: the SAME deterministic scoring the fallback path uses,
    # computed independently of which MCP tools the agent chose to call -
    # this is the "existing rule risk floor" step in the target architecture
    # (LLM reasoning -> proposed action -> rule risk floor -> governance),
    # not an MCP tool call, so it is never logged as one.
    health, _ = _timed(lambda: compute_campaign_health(db, campaign))
    vast_output, _ = _timed(lambda: _vast_validation_summary(db, campaign))
    brand_output, _ = _timed(lambda: _brand_safety_findings(db, campaign))
    policy_output, _ = _timed(lambda: _search_policy_context(f"{user_query} {health.main_suspected_issue}".strip()))

    risk_score, risk_level = _score_risk(health, vast_output, brand_output)
    rule_floor = {"LOW": "auto_recommend", "MEDIUM": "auto_recommend", "HIGH": "require_approval", "CRITICAL": "block"}[risk_level]
    top_cause = verified_causes[0]
    proposed_action = f"{top_cause.recommendation_title}: {top_cause.recommendation_description}"
    rationale = f"{outcome.diagnosis.diagnosis} {_build_rationale(health, vast_output, brand_output, policy_output)}"

    # Risk-routing gate: may only escalate the deterministic rule_floor, never
    # downgrade it (app.gates.base.apply_rule_floor enforces this unconditionally).
    routing = await risk_routing(
        run_id=run.id, campaign_id=campaign_id, rule_floor=rule_floor, proposed_action=proposed_action,
        evidence_summary={
            "risk_level": risk_level, "pacing_percentage": health.pacing_percentage,
            "vast_error_count": vast_output["vast_error_count"], "rejected_count": vast_output["rejected_count"],
            "brand_safety_finding_count": brand_output["finding_count"],
        },
        chain=gate_chain, settings=settings,
    )
    persist_gate_decision(
        db, agent_run_id=run.id, campaign_id=campaign_id, decision_point="risk_routing",
        result=routing.gate_result, rule_floor=rule_floor, final_decision=routing.final_routing,
        input_state={"proposed_action": proposed_action, "risk_level": risk_level},
    )

    approval_required = routing.final_routing in ("require_approval", "block")
    blocked = routing.final_routing == "block"

    # Client-safe-brief gate: an unsafe/needs-review brief is withheld, never
    # auto-released or silently rewritten (flag -> review -> audit).
    brief_check = await client_safe_brief_check(
        run_id=run.id, campaign_id=campaign_id, brief_text=outcome.diagnosis.client_safe_brief, chain=gate_chain,
    )
    persist_gate_decision(
        db, agent_run_id=run.id, campaign_id=campaign_id, decision_point="client_safe_brief",
        result=brief_check, rule_floor=None, final_decision=brief_check.decision,
        input_state={"brief_length": len(outcome.diagnosis.client_safe_brief)},
    )
    run.client_safe_brief_status = brief_check.decision
    run.client_safe_brief = outcome.diagnosis.client_safe_brief if brief_check.decision == "safe" else None

    # Approval/block rows follow the gate-adjusted final routing, not the raw
    # rule_floor directly - a gate escalation must actually route to a human,
    # not just be recorded and ignored.
    if blocked:
        db.add(
            BlockedAction(
                agent_run_id=run.id,
                tool_name="execute_proposed_action",
                reason=rationale,
                risk_level=risk_level,
            )
        )
    elif approval_required:
        db.add(
            ApprovalRequest(
                agent_run_id=run.id,
                campaign_id=campaign_id,
                proposed_action=proposed_action,
                risk_score=risk_score,
                risk_level=risk_level,
                rationale=rationale,
                status="pending",
            )
        )

    db.add(
        PolicyCheck(
            agent_run_id=run.id,
            policy_name=policy_output["matches"][0]["title"] if policy_output["matches"] else "No policy match",
            result="blocked" if blocked else "approval_required" if approval_required else (
                "review_required" if risk_level == "MEDIUM" else "clear"
            ),
            matched_rules=policy_output["matches"][0]["matched_keywords"] if policy_output["matches"] else [],
            citation=policy_output["matches"][0]["source"] if policy_output["matches"] else "no local policy match",
        )
    )

    if blocked:
        final_recommendation = (
            f"BLOCKED: {proposed_action} cannot execute automatically ({rationale}). "
            "Escalated for human review; no campaign changes were made."
        )
    elif approval_required:
        final_recommendation = (
            f"Recommend: {proposed_action} Routed for human approval before execution; "
            "no campaign changes were made."
        )
    else:
        final_recommendation = (
            f"Recommend: {proposed_action} No further governance escalation required; "
            "no campaign changes were made."
        )

    run.status = "completed"
    run.risk_level = risk_level
    run.risk_score = risk_score
    run.final_recommendation = final_recommendation
    run.approval_required = approval_required
    run.completed_at = utc_now()
    run.llm_provider = outcome.provider_name
    run.model_name = outcome.model_name
    run.input_tokens = outcome.total_input_tokens
    run.output_tokens = outcome.total_output_tokens
    run.total_tokens = outcome.total_tokens
    run.estimated_cost_usd = None  # never fabricated: neither provider SDK returns a $ cost here
    run.steps_used = outcome.steps_used
    db.add(run)
    db.commit()
    db.refresh(run)

    summary = f"Campaign {campaign_id} ({campaign.campaign_name}): {outcome.diagnosis.diagnosis}"

    return MCPAgentRunResponse(
        agent_run_id=str(run.id),
        status="completed",
        campaign_id=str(campaign_id),
        summary=summary,
        risk_score=risk_score,
        risk_level=risk_level,
        approval_required=approval_required,
        blocked=blocked,
        final_recommendation=final_recommendation,
        tool_timeline=_build_llm_timeline(run, outcome, approval_required=approval_required, blocked=blocked),
        execution_mode="llm_mcp_agent",
        llm_provider=outcome.provider_name,
        model_name=outcome.model_name,
        input_tokens=outcome.total_input_tokens,
        output_tokens=outcome.total_output_tokens,
        total_tokens=outcome.total_tokens,
        estimated_cost_usd=None,
        steps_used=outcome.steps_used,
        max_steps=settings.max_agent_steps,
        fallback_reason=None,
        tools_selected=outcome.tools_selected,
        client_safe_brief=run.client_safe_brief,
        client_safe_brief_status=run.client_safe_brief_status,
        gate_decisions=[GateDecisionRead.model_validate(item) for item in run.gate_decisions],
    )


def _build_llm_timeline(
    run: AgentRun, outcome: AgentRunOutcome, *, approval_required: bool, blocked: bool
) -> list[MCPToolTimelineEntry]:
    timeline = [
        MCPToolTimelineEntry(
            step=1,
            tool_name="create_agent_run",
            status="success",
            latency_ms=0,
            summary=(
                f"Created agent run {run.id} for campaign {run.campaign_id} "
                f"(llm_mcp_agent via {outcome.provider_name}/{outcome.model_name})."
            ),
        )
    ]
    for index, tool_outcome in enumerate(outcome.tool_outcomes, start=2):
        timeline.append(
            MCPToolTimelineEntry(
                step=index,
                tool_name=tool_outcome.tool_name,
                status="success" if tool_outcome.ok else "failed",
                latency_ms=tool_outcome.latency_ms,
                summary=(
                    "MCP tool call succeeded (real MCP protocol)."
                    if tool_outcome.ok
                    else f"MCP tool call failed: {tool_outcome.error_category}."
                ),
            )
        )
    next_step = len(outcome.tool_outcomes) + 2
    if blocked:
        timeline.append(
            MCPToolTimelineEntry(
                step=next_step, tool_name="create_blocked_action", status="success", latency_ms=0,
                summary="CRITICAL risk action blocked pending human review.",
            )
        )
    elif approval_required:
        timeline.append(
            MCPToolTimelineEntry(
                step=next_step, tool_name="create_approval_request", status="success", latency_ms=0,
                summary="HIGH risk action requires human approval before execution.",
            )
        )
    return timeline


def run_deterministic_fallback_orchestration(
    db: Session, campaign: Campaign, user_query: str, *, fallback_reason: str | None = None
) -> MCPAgentRunResponse:
    """The original, unchanged deterministic orchestration (no LLM, no MCP client
    - direct internal service calls, logged as mcp_tool_calls for backward-
    compatible audit shape). Now explicitly labeled execution_mode=
    "deterministic_fallback", with fallback_reason set whenever this ran
    because the governed LLM + MCP agent path was unavailable or failed."""
    campaign_id = campaign.id
    run = AgentRun(
        user_query=user_query.strip(),
        campaign_id=campaign_id,
        status="running",
        risk_level="LOW",
        risk_score=0.0,
        final_recommendation="",
        approval_required=False,
        execution_mode="deterministic_fallback",
        fallback_reason=fallback_reason,
    )
    db.add(run)
    db.flush()

    timeline: list[MCPToolTimelineEntry] = [
        MCPToolTimelineEntry(
            step=1,
            tool_name="create_agent_run",
            status="success",
            latency_ms=0,
            summary=f"Created agent run {run.id} for campaign {campaign_id}.",
        )
    ]

    def log_step(step_no: int, tool_name: str, input_json: dict[str, Any], output_json: dict[str, Any], latency_ms: int, summary: str) -> None:
        db.add(
            MCPToolCall(
                agent_run_id=run.id,
                tool_name=tool_name,
                input_json=input_json,
                output_json=output_json,
                status="success",
                latency_ms=latency_ms,
            )
        )
        timeline.append(
            MCPToolTimelineEntry(step=step_no, tool_name=tool_name, status="success", latency_ms=latency_ms, summary=summary)
        )

    try:
        health, health_latency = _timed(lambda: compute_campaign_health(db, campaign))
        health_output = {
            "risk_level": health.risk_level,
            "pacing_percentage": health.pacing_percentage,
            "creative_status": health.creative_status,
            "vast_error_count": health.vast_error_count,
            "main_suspected_issue": health.main_suspected_issue,
        }
        log_step(
            2, "get_campaign_health", {"campaign_id": campaign_id}, health_output, health_latency,
            f"Risk {health.risk_level}; pacing {health.pacing_percentage}%; {health.main_suspected_issue}.",
        )

        pacing_output, pacing_latency = _timed(lambda: _pacing_snapshot_summary(db, campaign))
        log_step(
            3, "get_campaign_pacing", {"campaign_id": campaign_id}, pacing_output, pacing_latency,
            f"Latest pacing {pacing_output['pacing_percentage']}% ({pacing_output['risk_level']} risk)."
            if pacing_output["found"] else "No pacing snapshots found.",
        )

        vast_output, vast_latency = _timed(lambda: _vast_validation_summary(db, campaign))
        log_step(
            4, "get_vast_validation_summary", {"campaign_id": campaign_id}, vast_output, vast_latency,
            f"{vast_output['creative_count']} creatives; {vast_output['rejected_count']} rejected; "
            f"{vast_output['vast_error_count']} VAST errors.",
        )

        brand_output, brand_latency = _timed(lambda: _brand_safety_findings(db, campaign))
        log_step(
            5, "get_brand_safety_findings", {"campaign_id": campaign_id}, brand_output, brand_latency,
            f"{brand_output['finding_count']} brand-safety finding(s) identified."
            if brand_output["finding_count"] else "No brand-safety findings identified.",
        )

        policy_query = f"{user_query} {health.main_suspected_issue}".strip()
        policy_output, policy_latency = _timed(lambda: _search_policy_context(policy_query))
        log_step(
            6, "search_policy_context", {"query": policy_query}, policy_output, policy_latency,
            f"{len(policy_output['matches'])} policy document(s) matched." if policy_output["matches"]
            else "No policy documents matched the query.",
        )
    except Exception as exc:  # defensive boundary: never let orchestration 500 mid-run
        run.status = "failed"
        run.risk_level = "LOW"
        run.risk_score = 0.0
        run.approval_required = False
        run.final_recommendation = (
            f"Agent run failed during governance data collection: {exc}. No campaign changes were made."
        )
        run.completed_at = utc_now()
        db.add(run)
        db.commit()
        db.refresh(run)
        return MCPAgentRunResponse(
            agent_run_id=str(run.id),
            status="failed",
            campaign_id=str(campaign_id),
            summary=run.final_recommendation,
            risk_score=0.0,
            risk_level="LOW",
            approval_required=False,
            blocked=False,
            final_recommendation=run.final_recommendation,
            tool_timeline=timeline,
            execution_mode=run.execution_mode,
            fallback_reason=run.fallback_reason,
        )

    risk_score, risk_level = _score_risk(health, vast_output, brand_output)
    proposed_action = _derive_proposed_action(db, campaign, health)
    rationale = _build_rationale(health, vast_output, brand_output, policy_output)

    approval_required = risk_level in ("HIGH", "CRITICAL")
    blocked = risk_level == "CRITICAL"

    if risk_level == "HIGH":
        db.add(
            ApprovalRequest(
                agent_run_id=run.id,
                campaign_id=campaign_id,
                proposed_action=proposed_action,
                risk_score=risk_score,
                risk_level=risk_level,
                rationale=rationale,
                status="pending",
            )
        )
        timeline.append(
            MCPToolTimelineEntry(
                step=7, tool_name="create_approval_request", status="success", latency_ms=0,
                summary="HIGH risk action requires human approval before execution.",
            )
        )
    elif risk_level == "CRITICAL":
        db.add(
            BlockedAction(
                agent_run_id=run.id,
                tool_name="execute_proposed_action",
                reason=rationale,
                risk_level=risk_level,
            )
        )
        timeline.append(
            MCPToolTimelineEntry(
                step=7, tool_name="create_blocked_action", status="success", latency_ms=0,
                summary="CRITICAL risk action blocked pending human review.",
            )
        )

    db.add(
        PolicyCheck(
            agent_run_id=run.id,
            policy_name=policy_output["matches"][0]["title"] if policy_output["matches"] else "No policy match",
            result="blocked" if blocked else "approval_required" if approval_required else (
                "review_required" if risk_level == "MEDIUM" else "clear"
            ),
            matched_rules=policy_output["matches"][0]["matched_keywords"] if policy_output["matches"] else [],
            citation=policy_output["matches"][0]["source"] if policy_output["matches"] else "no local policy match",
        )
    )

    summary = (
        f"Campaign {campaign_id} ({campaign.campaign_name}): {health.main_suspected_issue}. "
        f"Pacing {health.pacing_percentage}%, {vast_output['vast_error_count']} VAST errors, "
        f"{brand_output['finding_count']} brand-safety findings."
    )

    if blocked:
        final_recommendation = (
            f"BLOCKED: {proposed_action} cannot execute automatically ({rationale}). "
            "Escalated for human review; no campaign changes were made."
        )
    elif approval_required:
        final_recommendation = (
            f"Recommend: {proposed_action} Routed for human approval before execution; "
            "no campaign changes were made."
        )
    else:
        final_recommendation = (
            f"Recommend: {proposed_action} No further governance escalation required; "
            "no campaign changes were made."
        )

    run.status = "completed"
    run.risk_level = risk_level
    run.risk_score = risk_score
    run.final_recommendation = final_recommendation
    run.approval_required = approval_required
    run.completed_at = utc_now()
    db.add(run)
    db.commit()
    db.refresh(run)

    return MCPAgentRunResponse(
        agent_run_id=str(run.id),
        status="completed",
        campaign_id=str(campaign_id),
        summary=summary,
        risk_score=risk_score,
        risk_level=risk_level,
        approval_required=approval_required,
        blocked=blocked,
        final_recommendation=final_recommendation,
        tool_timeline=timeline,
        execution_mode=run.execution_mode,
        fallback_reason=run.fallback_reason,
    )
