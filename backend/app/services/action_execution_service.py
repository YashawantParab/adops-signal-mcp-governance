"""The closed synthetic action loop (Phase 3): propose -> gate -> pending_approval
-> approved -> executed -> verified, with human-authorized rollback. All
business logic lives here - API handlers only translate HTTP <-> these calls.

Hard rules enforced in this module, not just documented:
  - an action can never execute without status == "approved"
  - CRITICAL risk_class can never reach "approved" (blocked at proposal, and
    re-checked at execution as defense in depth)
  - execution requires a real reviewer (approval_request.reviewer_id set) -
    the agent identity can propose, it can never be the reviewer
  - a materially changed campaign state since approval invalidates the
    approval (state_version mismatch) rather than silently executing against
    now-stale assumptions

Every public function here ends its successful/terminal paths with
`db.commit()` - get_db() never commits on its own (only closes the session),
so without this every write here silently vanished the moment the request
ended (a real bug found and fixed during live end-to-end validation: every
/api/actions/* write endpoint returned a plausible 200, but nothing survived
past that single request). SessionLocal is also configured with
expire_on_commit=False (for cheap post-commit response serialization
elsewhere in the app), so a `db.commit()` here does NOT invalidate an
already-loaded object's relationship collections from earlier in the same
session/request - `db.expire_all()` immediately after each commit closes
that gap so the caller's next read is guaranteed fresh.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    ActionExecution,
    ActionRollback,
    ActionVerification,
    ApprovalRequest,
    Campaign,
    ProposedAction,
    User,
)
from app.security import DEMO_VIEWER_ROLE
from app.services import mock_ad_server
from app.services.campaign_service import get_campaign_health as compute_campaign_health, get_campaign_or_none
from app.services.mcp_governance_service import _brand_safety_findings, _score_risk, _vast_validation_summary
from app.time_utils import utc_now

_LEVEL_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


class ActionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CampaignNotFoundError(ActionError):
    def __init__(self, campaign_id: int) -> None:
        super().__init__("CAMPAIGN_NOT_FOUND", f"Campaign {campaign_id} was not found")


def _campaign_risk_level(db: Session, campaign: Campaign) -> str:
    health = compute_campaign_health(db, campaign)
    vast_result = _vast_validation_summary(db, campaign)
    brand_result = _brand_safety_findings(db, campaign)
    _, risk_level = _score_risk(health, vast_result, brand_result)
    return risk_level


def _hash_state(fields: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(fields, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def propose_action(
    db: Session, *, campaign_id: int, action_type: str, requested_params: dict[str, Any],
    agent_run_id: int | None = None, proposed_by: str = "agent",
) -> ProposedAction:
    campaign = get_campaign_or_none(db, campaign_id)
    if campaign is None:
        raise CampaignNotFoundError(campaign_id)

    mock_ad_server.validate_params(action_type, requested_params)
    campaign_risk_level = _campaign_risk_level(db, campaign)
    base_risk = mock_ad_server.BASE_RISK_CLASS[action_type]
    risk_class = max(base_risk, campaign_risk_level, key=lambda level: _LEVEL_ORDER[level])

    action = ProposedAction(
        campaign_id=campaign_id,
        agent_run_id=agent_run_id,
        action_type=action_type,
        requested_params=requested_params,
        risk_class=risk_class,
        status="blocked" if risk_class == "CRITICAL" else "pending_approval",
        proposed_by=proposed_by,
    )
    db.add(action)
    db.commit()
    db.expire_all()  # see module docstring: expire_on_commit=False needs an explicit expire after commit

    if risk_class == "CRITICAL":
        return action  # CRITICAL never reaches an approval queue - matches BlockedAction semantics elsewhere

    before = mock_ad_server.read_state(campaign, action_type)
    action.state_version = _hash_state(before.fields)

    approval = ApprovalRequest(
        campaign_id=campaign_id,
        agent_run_id=agent_run_id if agent_run_id is not None else _placeholder_agent_run(db, campaign_id),
        proposed_action=f"{action_type}: {json.dumps(requested_params)}",
        risk_score={"LOW": 10.0, "MEDIUM": 40.0, "HIGH": 70.0}[risk_class],
        risk_level=risk_class,
        rationale=f"Synthetic action proposed by {proposed_by} against campaign {campaign_id}.",
        status="pending",
    )
    db.add(approval)
    db.flush()
    action.approval_request_id = approval.id
    db.add(action)
    db.commit()
    db.expire_all()  # see module docstring: expire_on_commit=False needs an explicit expire after commit
    return action


def _placeholder_agent_run(db: Session, campaign_id: int) -> int:
    """ApprovalRequest.agent_run_id is NOT NULL (Phase 0 schema) - an
    operator-proposed action with no originating agent run needs a real row to
    point at. Reuses the existing agent_runs table rather than loosening a
    constraint that every other caller relies on being non-null."""
    from app.models import AgentRun

    run = AgentRun(
        user_query="[synthetic action proposal - no diagnosis run]",
        campaign_id=campaign_id, status="completed", risk_level="LOW", risk_score=0.0,
        final_recommendation="N/A - operator-proposed synthetic action.", approval_required=False,
        execution_mode="deterministic_fallback",
    )
    db.add(run)
    db.flush()
    return run.id


def approve_action(db: Session, proposed_action_id: int, *, reviewer: User, rationale: str) -> ProposedAction:
    action = db.get(ProposedAction, proposed_action_id)
    if action is None:
        raise ActionError("ACTION_NOT_FOUND", f"Proposed action {proposed_action_id} was not found")
    if action.status != "pending_approval":
        raise ActionError("INVALID_STATE", f"Action {proposed_action_id} is '{action.status}', not pending_approval")
    if reviewer.role == DEMO_VIEWER_ROLE:
        raise ActionError("FORBIDDEN", "The public demo role cannot approve actions")

    approval = db.get(ApprovalRequest, action.approval_request_id)
    if approval is None or approval.status != "pending":
        raise ActionError("INVALID_STATE", "Linked approval request is missing or already decided")

    approval.status = "approved"
    approval.reviewer_id = reviewer.id
    approval.reviewed_at = utc_now()
    approval.rationale = rationale.strip()
    db.add(approval)

    action.status = "approved"
    db.add(action)
    db.commit()
    db.expire_all()  # see module docstring: expire_on_commit=False needs an explicit expire after commit
    return action


def execute_action(db: Session, proposed_action_id: int, *, executor: User) -> ActionExecution:
    action = db.execute(
        select(ProposedAction)
        .where(ProposedAction.id == proposed_action_id)
        .options(selectinload(ProposedAction.approval_request), selectinload(ProposedAction.campaign))
    ).scalar_one_or_none()
    if action is None:
        raise ActionError("ACTION_NOT_FOUND", f"Proposed action {proposed_action_id} was not found")
    if action.status != "approved":
        raise ActionError("NOT_APPROVED", f"Action {proposed_action_id} is '{action.status}', not approved - it cannot execute")
    if action.risk_class == "CRITICAL":
        raise ActionError("CRITICAL_BLOCKED", "CRITICAL-risk actions can never execute")  # defense in depth
    if executor.role == DEMO_VIEWER_ROLE:
        raise ActionError("FORBIDDEN", "The public demo role cannot execute actions")

    approval = action.approval_request
    if approval is None or approval.status != "approved" or not approval.reviewer_id:
        raise ActionError("NOT_APPROVED", "Action has no valid human-reviewed approval")

    campaign = action.campaign
    current_state = mock_ad_server.read_state(campaign, action.action_type)
    if action.state_version and _hash_state(current_state.fields) != action.state_version:
        action.status = "failed"
        db.add(action)
        db.commit()
        db.expire_all()  # see module docstring: expire_on_commit=False needs an explicit expire after commit
        raise ActionError(
            "STALE_APPROVAL",
            "Campaign state changed materially since this action was approved - re-propose and re-approve before executing",
        )

    before_state = current_state
    target_state = mock_ad_server.requested_state(action.action_type, action.requested_params, before_state)

    try:
        mock_ad_server.apply_state(db, campaign, target_state)
        after_state = mock_ad_server.read_state(campaign, action.action_type)
        execution = ActionExecution(
            proposed_action_id=action.id, executed_by=executor.id,
            before_state=before_state.fields, after_state=after_state.fields, status="executed",
        )
        db.add(execution)
        action.status = "executed"
        db.add(action)
        db.flush()
    except Exception as exc:  # the mock write itself should never fail, but never silently swallow if it does
        action.status = "failed"
        db.add(action)
        db.commit()
        db.expire_all()  # see module docstring: expire_on_commit=False needs an explicit expire after commit
        raise ActionError("EXECUTION_FAILED", str(exc)) from exc

    _verify_execution(db, execution, expected=target_state)
    return execution


def _verify_execution(db: Session, execution: ActionExecution, *, expected: mock_ad_server.ActionState) -> ActionVerification:
    actual = mock_ad_server.ActionState(fields=execution.after_state)
    matched = mock_ad_server.states_match(expected, actual)
    verification = ActionVerification(
        action_execution_id=execution.id,
        expected_state=expected.fields,
        actual_state=actual.fields,
        verification_status="verified" if matched else "mismatch",
        mismatch_reason=None if matched else f"expected {expected.fields}, actual {actual.fields}",
    )
    db.add(verification)
    if matched:
        execution.proposed_action.status = "verified"
        db.add(execution.proposed_action)
    db.commit()
    db.expire_all()  # see module docstring: expire_on_commit=False needs an explicit expire after commit
    return verification


def rollback_action(db: Session, action_execution_id: int, *, actor: User) -> ActionRollback:
    execution = db.execute(
        select(ActionExecution)
        .where(ActionExecution.id == action_execution_id)
        .options(selectinload(ActionExecution.proposed_action).selectinload(ProposedAction.campaign))
    ).scalar_one_or_none()
    if execution is None:
        raise ActionError("EXECUTION_NOT_FOUND", f"Action execution {action_execution_id} was not found")
    if execution.status != "executed":
        raise ActionError("INVALID_STATE", "Only a successfully executed action can be rolled back")
    if actor.role == DEMO_VIEWER_ROLE:
        raise ActionError("FORBIDDEN", "The public demo role cannot roll back actions")

    proposed_action = execution.proposed_action
    campaign = proposed_action.campaign
    restore_state = mock_ad_server.ActionState(fields=execution.before_state)
    mock_ad_server.apply_state(db, campaign, restore_state)
    actual_after = mock_ad_server.read_state(campaign, proposed_action.action_type)
    matched = mock_ad_server.states_match(restore_state, actual_after)

    rollback = ActionRollback(
        action_execution_id=execution.id, rolled_back_by=actor.id,
        restored_state=restore_state.fields, actual_state_after=actual_after.fields,
        verification_status="verified" if matched else "mismatch",
    )
    db.add(rollback)
    proposed_action.status = "rolled_back"
    db.add(proposed_action)
    db.commit()
    db.expire_all()  # see module docstring: expire_on_commit=False needs an explicit expire after commit
    return rollback
