import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.mcp import (
    approve_mcp_approval,
    mcp_approvals,
    mcp_governance_summary,
    mcp_run_detail,
    mcp_runs,
    mcp_tools,
    reject_mcp_approval,
    run_mcp_agent,
)
from app.database import Base
from app.models import (
    AdRequest,
    Advertiser,
    AgentRun,
    ApprovalRequest,
    BidResponse,
    BlockedAction,
    Campaign,
    Creative,
    Impression,
    InventorySegment,
    MCPToolCall,
    PacingSnapshot,
    PolicyCheck,
    Publisher,
    Recommendation,
    User,
    VastValidationError,
)
from app.schemas import MCPAgentRunRequest, MCPApprovalDecisionRequest
from seed import build_seed_data


def seeded_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'mcp-governance.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    data = build_seed_data()
    for key in [
        "users",
        "advertisers",
        "publishers",
        "inventory_segments",
        "campaigns",
        "creatives",
        "vast_validation_errors",
        "ad_requests",
        "impressions",
        "bid_responses",
        "pacing_snapshots",
        "recommendations",
        "agent_runs",
        "mcp_tool_calls",
        "approval_requests",
        "policy_checks",
        "blocked_actions",
    ]:
        db.add_all(data[key])
        db.flush()
    db.commit()
    return db


def test_seed_contains_required_mcp_governance_volume(tmp_path):
    db = seeded_session(tmp_path)

    assert db.query(AgentRun).count() >= 8
    assert db.query(MCPToolCall).count() >= 25
    assert db.query(ApprovalRequest).count() >= 5
    assert db.query(PolicyCheck).count() >= 4
    assert db.query(BlockedAction).count() >= 3


def test_mcp_runs_and_detail_are_structured(tmp_path):
    db = seeded_session(tmp_path)
    user = db.get(User, 1)

    runs = mcp_runs(db=db, _=user)
    detail = mcp_run_detail(9001, db=db, _=user)

    assert len(runs) >= 8
    assert runs[0].created_at >= runs[-1].created_at
    assert detail.id == 9001
    assert detail.campaign_name == "RheinAuto CTV Launch"
    assert detail.tool_calls
    assert detail.approval_requests
    assert detail.policy_checks


def test_mcp_approval_decision_updates_only_approval_request(tmp_path):
    db = seeded_session(tmp_path)
    user = db.get(User, 1)
    campaign_before = db.get(Campaign, 1045)
    original_budget = campaign_before.budget
    original_status = campaign_before.status

    result = approve_mcp_approval(
        9201,
        MCPApprovalDecisionRequest(rationale="Evidence reviewed; approve controlled expansion planning."),
        db=db,
        user=user,
    )
    campaign_after = db.get(Campaign, 1045)

    assert result.status == "approved"
    assert result.reviewer_id == user.id
    assert result.reviewed_at is not None
    assert campaign_after.budget == original_budget
    assert campaign_after.status == original_status


def test_mcp_approval_reject_and_conflict(tmp_path):
    db = seeded_session(tmp_path)
    user = db.get(User, 4)

    result = reject_mcp_approval(
        9203,
        MCPApprovalDecisionRequest(rationale="Reject until gaming suitability review is completed."),
        db=db,
        user=user,
    )
    assert result.status == "rejected"

    with pytest.raises(HTTPException) as excinfo:
        reject_mcp_approval(
            9203,
            MCPApprovalDecisionRequest(rationale="Second decision should fail."),
            db=db,
            user=user,
        )
    assert excinfo.value.status_code == 409


def test_mcp_tools_and_summary(tmp_path):
    db = seeded_session(tmp_path)
    user = db.get(User, 2)

    tools = mcp_tools(db=db, _=user)
    summary = mcp_governance_summary(db=db, _=user)

    assert any(tool.name == "get_campaign_pacing" and tool.read_only for tool in tools)
    pacing_tool = next(tool for tool in tools if tool.name == "get_campaign_pacing")
    assert pacing_tool.category == "Campaign Signals"
    assert pacing_tool.call_count > 0
    assert pacing_tool.last_used_at is not None
    assert summary.total_runs == 8
    assert summary.tool_calls >= 25
    assert summary.approval_requests["pending"] >= 3
    assert summary.blocked_actions >= 3


def test_mcp_run_not_found_returns_404(tmp_path):
    db = seeded_session(tmp_path)
    user = db.get(User, 1)

    with pytest.raises(HTTPException) as excinfo:
        mcp_run_detail(999999, db=db, _=user)
    assert excinfo.value.status_code == 404


def test_agent_run_high_risk_creates_approval_request(tmp_path):
    db = seeded_session(tmp_path)
    user = db.get(User, 1)
    campaign_before = db.get(Campaign, 1045)
    original_budget = campaign_before.budget
    original_status = campaign_before.status

    result = run_mcp_agent(
        MCPAgentRunRequest(user_query="Why is RheinAuto behind pacing?", campaign_id="1045"),
        db=db,
        _=user,
    )

    assert result.status == "completed"
    assert result.campaign_id == "1045"
    assert result.risk_level == "HIGH"
    assert result.approval_required is True
    assert result.blocked is False
    assert len(result.tool_timeline) == 7  # create_run + 5 reads + create_approval_request
    assert [entry.tool_name for entry in result.tool_timeline[1:6]] == [
        "get_campaign_health",
        "get_campaign_pacing",
        "get_vast_validation_summary",
        "get_brand_safety_findings",
        "search_policy_context",
    ]

    run = db.get(AgentRun, int(result.agent_run_id))
    assert run.status == "completed"
    assert run.risk_level == "HIGH"
    assert db.query(MCPToolCall).filter_by(agent_run_id=run.id).count() == 5
    assert db.query(ApprovalRequest).filter_by(agent_run_id=run.id).count() == 1
    assert db.query(BlockedAction).filter_by(agent_run_id=run.id).count() == 0
    assert db.query(PolicyCheck).filter_by(agent_run_id=run.id).count() == 1

    campaign_after = db.get(Campaign, 1045)
    assert campaign_after.budget == original_budget
    assert campaign_after.status == original_status


def test_agent_run_critical_risk_creates_blocked_action(tmp_path):
    db = seeded_session(tmp_path)
    user = db.get(User, 1)

    result = run_mcp_agent(
        MCPAgentRunRequest(user_query="Can the rejected NordicStream creative serve?", campaign_id="1046"),
        db=db,
        _=user,
    )

    assert result.status == "completed"
    assert result.risk_level == "CRITICAL"
    assert result.approval_required is True
    assert result.blocked is True
    assert "BLOCKED" in result.final_recommendation

    run = db.get(AgentRun, int(result.agent_run_id))
    assert db.query(BlockedAction).filter_by(agent_run_id=run.id).count() == 1
    assert db.query(ApprovalRequest).filter_by(agent_run_id=run.id).count() == 0


def test_agent_run_low_risk_creates_no_governance_escalation(tmp_path):
    db = seeded_session(tmp_path)
    user = db.get(User, 1)

    result = run_mcp_agent(
        MCPAgentRunRequest(user_query="Is LuxeHome healthy and pacing on plan?", campaign_id="1047"),
        db=db,
        _=user,
    )

    assert result.status == "completed"
    assert result.risk_level == "LOW"
    assert result.approval_required is False
    assert result.blocked is False

    run = db.get(AgentRun, int(result.agent_run_id))
    assert db.query(ApprovalRequest).filter_by(agent_run_id=run.id).count() == 0
    assert db.query(BlockedAction).filter_by(agent_run_id=run.id).count() == 0


def test_agent_run_invalid_campaign_id_returns_422(tmp_path):
    db = seeded_session(tmp_path)
    user = db.get(User, 1)

    with pytest.raises(HTTPException) as excinfo:
        run_mcp_agent(
            MCPAgentRunRequest(user_query="Why is this campaign behind pacing?", campaign_id="not-a-number"),
            db=db,
            _=user,
        )
    assert excinfo.value.status_code == 422


def test_agent_run_unknown_campaign_returns_404(tmp_path):
    db = seeded_session(tmp_path)
    user = db.get(User, 1)

    with pytest.raises(HTTPException) as excinfo:
        run_mcp_agent(
            MCPAgentRunRequest(user_query="Why is this campaign behind pacing?", campaign_id="999999"),
            db=db,
            _=user,
        )
    assert excinfo.value.status_code == 404
