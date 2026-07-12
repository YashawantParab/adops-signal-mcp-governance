from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import (
    AgentRunDetail,
    AgentRunRead,
    ApprovalRequestRead,
    MCPAgentRunRequest,
    MCPAgentRunResponse,
    MCPApprovalDecisionRequest,
    MCPSummary,
    MCPToolRead,
)
from app.security import DEMO_VIEWER_ROLE, get_current_user, require_roles
from app.services.mcp_governance_service import (
    ApprovalRequestAlreadyDecidedError,
    CampaignNotFoundError,
    InvalidCampaignIdError,
    decide_approval_request,
    get_agent_run_detail,
    list_agent_runs,
    list_approval_requests,
    mcp_summary,
    mcp_tool_registry,
    run_agent_orchestration,
)

router = APIRouter(prefix="/api/mcp", tags=["mcp-governance"])


@router.get("/runs", response_model=list[AgentRunRead])
def mcp_runs(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "adops_manager", "product_manager", DEMO_VIEWER_ROLE)),
) -> list[AgentRunRead]:
    return list_agent_runs(db)


@router.get("/runs/{run_id}", response_model=AgentRunDetail)
def mcp_run_detail(
    run_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "adops_manager", "product_manager", DEMO_VIEWER_ROLE)),
) -> AgentRunDetail:
    run = get_agent_run_detail(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="MCP agent run not found")
    return run


@router.get("/approvals", response_model=list[ApprovalRequestRead])
def mcp_approvals(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "adops_manager", "product_manager", DEMO_VIEWER_ROLE)),
) -> list[ApprovalRequestRead]:
    return list_approval_requests(db)


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRequestRead)
def approve_mcp_approval(
    approval_id: int,
    payload: MCPApprovalDecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "adops_manager")),
) -> ApprovalRequestRead:
    try:
        approval = decide_approval_request(
            db,
            approval_id,
            "approved",
            reviewer=user,
            rationale=payload.rationale,
        )
    except ApprovalRequestAlreadyDecidedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
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
        reviewer_name=user.full_name,
        reviewed_at=approval.reviewed_at,
        created_at=approval.created_at,
    )


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRequestRead)
def reject_mcp_approval(
    approval_id: int,
    payload: MCPApprovalDecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "adops_manager")),
) -> ApprovalRequestRead:
    try:
        approval = decide_approval_request(
            db,
            approval_id,
            "rejected",
            reviewer=user,
            rationale=payload.rationale,
        )
    except ApprovalRequestAlreadyDecidedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
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
        reviewer_name=user.full_name,
        reviewed_at=approval.reviewed_at,
        created_at=approval.created_at,
    )


@router.post("/agent/run", response_model=MCPAgentRunResponse)
def run_mcp_agent(
    payload: MCPAgentRunRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "adops_manager", "product_manager", DEMO_VIEWER_ROLE)),
) -> MCPAgentRunResponse:
    try:
        return run_agent_orchestration(db, payload.user_query, payload.campaign_id)
    except InvalidCampaignIdError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tools", response_model=list[MCPToolRead])
def mcp_tools(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[MCPToolRead]:
    return mcp_tool_registry(db)


@router.get("/summary", response_model=MCPSummary)
def mcp_governance_summary(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "adops_manager", "product_manager", DEMO_VIEWER_ROLE)),
) -> MCPSummary:
    return mcp_summary(db)
