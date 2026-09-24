"""Tests for the closed synthetic action loop (Phase 3): propose -> approve ->
execute -> verify -> rollback, and the hard rules that must hold regardless of
UI: unapproved actions cannot execute, CRITICAL actions cannot execute, the
public demo role cannot approve/execute/rollback, and a materially changed
campaign invalidates a stale approval.
"""
from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import pytest

from app.database import Base
from app.models import (
    ActionExecution,
    ActionRollback,
    ActionVerification,
    ApprovalRequest,
    Campaign,
    ProposedAction,
    User,
)
from app.security import build_demo_viewer
from app.services.action_execution_service import (
    ActionError,
    approve_action,
    execute_action,
    propose_action,
    rollback_action,
)
from seed import build_seed_data


def seeded_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'actions.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    data = build_seed_data()
    for key in [
        "users", "advertisers", "publishers", "inventory_segments", "campaigns",
        "creatives", "vast_validation_errors", "ad_requests", "impressions",
        "bid_responses", "pacing_snapshots", "recommendations",
    ]:
        db.add_all(data[key])
        db.flush()
    db.commit()
    return db


def reviewer(db):
    return db.get(User, 1)  # adops_manager, per seed.py


def test_full_lifecycle_propose_approve_execute_verify_rollback(tmp_path):
    db = seeded_session(tmp_path)
    campaign_before = db.get(Campaign, 1047)  # LOW risk
    original_cap = campaign_before.frequency_cap

    action = propose_action(db, campaign_id=1047, action_type="adjust_frequency_cap", requested_params={"new_frequency_cap": 5})
    assert action.status == "pending_approval"
    assert action.risk_class in ("LOW", "MEDIUM")

    approval = db.get(ApprovalRequest, action.approval_request_id)
    assert approval.status == "pending"

    action = approve_action(db, action.id, reviewer=reviewer(db), rationale="Reviewed pacing forecast; approved.")
    assert action.status == "approved"

    execution = execute_action(db, action.id, executor=reviewer(db))
    assert execution.status == "executed"

    campaign_after = db.get(Campaign, 1047)
    assert campaign_after.frequency_cap == 5
    assert campaign_after.frequency_cap != original_cap

    action_after = db.get(ProposedAction, action.id)
    assert action_after.status == "verified"

    verification = db.execute(select(ActionVerification).where(ActionVerification.action_execution_id == execution.id)).scalar_one()
    assert verification.verification_status == "verified"
    assert verification.actual_state == {"frequency_cap": 5}

    rollback = rollback_action(db, execution.id, actor=reviewer(db))
    assert rollback.verification_status == "verified"

    campaign_restored = db.get(Campaign, 1047)
    assert campaign_restored.frequency_cap == original_cap

    action_final = db.get(ProposedAction, action.id)
    assert action_final.status == "rolled_back"


def test_unapproved_action_cannot_execute(tmp_path):
    db = seeded_session(tmp_path)
    original_cap = db.get(Campaign, 1047).frequency_cap
    requested_cap = original_cap + 1 if original_cap < 20 else original_cap - 1

    action = propose_action(db, campaign_id=1047, action_type="adjust_frequency_cap", requested_params={"new_frequency_cap": requested_cap})
    assert action.status == "pending_approval"

    with pytest.raises(ActionError) as excinfo:
        execute_action(db, action.id, executor=reviewer(db))
    assert excinfo.value.code == "NOT_APPROVED"

    campaign = db.get(Campaign, 1047)
    assert campaign.frequency_cap == original_cap  # nothing changed


def test_critical_campaign_action_is_blocked_at_proposal_and_cannot_execute(tmp_path):
    db = seeded_session(tmp_path)
    # Campaign 1046 has a rejected creative + brand-safety finding -> CRITICAL,
    # per the existing deterministic risk engine (see test_mcp_governance_api.py).
    action = propose_action(db, campaign_id=1046, action_type="relax_device_constraint", requested_params={"add_device": "Mobile"})
    assert action.status == "blocked"
    assert action.risk_class == "CRITICAL"
    assert action.approval_request_id is None  # never queued for approval

    with pytest.raises(ActionError) as excinfo:
        execute_action(db, action.id, executor=reviewer(db))
    assert excinfo.value.code == "NOT_APPROVED"  # blocked, not approved - can't reach execution either way


def test_critical_risk_class_defense_in_depth_even_if_somehow_approved(tmp_path):
    """Simulates a hypothetical bug upstream that let a CRITICAL action reach
    status=approved - execute_action must still refuse to run it."""
    db = seeded_session(tmp_path)
    action = ProposedAction(
        campaign_id=1045, action_type="pause_campaign", requested_params={},
        risk_class="CRITICAL", status="approved", proposed_by="agent",
    )
    db.add(action)
    db.flush()

    with pytest.raises(ActionError) as excinfo:
        execute_action(db, action.id, executor=reviewer(db))
    assert excinfo.value.code == "CRITICAL_BLOCKED"


def test_demo_viewer_cannot_approve_execute_or_rollback(tmp_path):
    db = seeded_session(tmp_path)
    demo_user = build_demo_viewer()
    action = propose_action(db, campaign_id=1047, action_type="adjust_frequency_cap", requested_params={"new_frequency_cap": 6})

    with pytest.raises(ActionError) as excinfo:
        approve_action(db, action.id, reviewer=demo_user, rationale="should not be allowed")
    assert excinfo.value.code == "FORBIDDEN"

    action = approve_action(db, action.id, reviewer=reviewer(db), rationale="approved by a real reviewer")
    with pytest.raises(ActionError) as excinfo:
        execute_action(db, action.id, executor=demo_user)
    assert excinfo.value.code == "FORBIDDEN"

    execution = execute_action(db, action.id, executor=reviewer(db))
    with pytest.raises(ActionError) as excinfo:
        rollback_action(db, execution.id, actor=demo_user)
    assert excinfo.value.code == "FORBIDDEN"


def test_stale_approval_blocks_execution_after_campaign_state_drifts(tmp_path):
    db = seeded_session(tmp_path)
    action = propose_action(db, campaign_id=1047, action_type="adjust_frequency_cap", requested_params={"new_frequency_cap": 7})
    action = approve_action(db, action.id, reviewer=reviewer(db), rationale="approved")

    # Simulate the campaign's frequency_cap changing through some other path
    # after approval but before execution.
    campaign = db.get(Campaign, 1047)
    campaign.frequency_cap = 999
    db.add(campaign)
    db.commit()

    with pytest.raises(ActionError) as excinfo:
        execute_action(db, action.id, executor=reviewer(db))
    assert excinfo.value.code == "STALE_APPROVAL"

    action_after = db.get(ProposedAction, action.id)
    assert action_after.status == "failed"


def test_relax_device_constraint_adds_device_without_duplicating(tmp_path):
    db = seeded_session(tmp_path)
    from app.services.json_fields import parse_list
    from app.services.mock_ad_server import KNOWN_DEVICES

    campaign = db.get(Campaign, 1047)
    existing = parse_list(campaign.target_devices)
    missing_device = next(device for device in KNOWN_DEVICES if device not in existing)

    action = propose_action(db, campaign_id=1047, action_type="relax_device_constraint", requested_params={"add_device": missing_device})
    action = approve_action(db, action.id, reviewer=reviewer(db), rationale="approved")
    execute_action(db, action.id, executor=reviewer(db))

    campaign_after = db.get(Campaign, 1047)
    devices = parse_list(campaign_after.target_devices)
    assert missing_device in devices
    assert devices.count(missing_device) == 1
    assert set(existing).issubset(set(devices))  # existing devices preserved, not clobbered


def test_pause_and_resume_campaign_round_trip(tmp_path):
    db = seeded_session(tmp_path)
    action = propose_action(db, campaign_id=1047, action_type="pause_campaign", requested_params={})
    assert action.risk_class == "HIGH"  # pause is always HIGH base risk
    action = approve_action(db, action.id, reviewer=reviewer(db), rationale="approved to stop delivery")
    execute_action(db, action.id, executor=reviewer(db))
    assert db.get(Campaign, 1047).status == "paused"

    resume = propose_action(db, campaign_id=1047, action_type="resume_campaign", requested_params={})
    resume = approve_action(db, resume.id, reviewer=reviewer(db), rationale="resuming")
    execute_action(db, resume.id, executor=reviewer(db))
    assert db.get(Campaign, 1047).status == "active"
