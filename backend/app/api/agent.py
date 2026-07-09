from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import AdOpsSignalAgent
from app.agent.tool_registry import list_tools
from app.database import get_db
from app.models import AgentAuditLog, User
from app.schemas import (
    AgentDiagnoseRequest,
    AgentDiagnoseResponse,
    AuditLogRead,
    ClientSummaryRequest,
    ClientSummaryResponse,
    ToolDescriptorRead,
    VastValidationRequest,
    VastValidationResponse,
)
from app.rate_limit import check_rate_limit
from app.services.campaign_service import get_campaign_or_none
from app.services.json_fields import parse_json
from app.services.vast_service import validate_vast
from app.security import DEMO_VIEWER_ROLE, get_current_user, require_roles

router = APIRouter(prefix="/api/agent", tags=["agent"])
agent = AdOpsSignalAgent()
DEMO_DIAGNOSE_RATE_LIMIT_PER_MINUTE = 10


def _enforce_demo_rate_limit(user: User, request: Request) -> None:
    if user.role != DEMO_VIEWER_ROLE:
        return
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(f"demo-diagnose:{client_ip}", DEMO_DIAGNOSE_RATE_LIMIT_PER_MINUTE):
        raise HTTPException(status_code=429, detail="Public demo diagnosis rate limit reached. Try again shortly.")


@router.post("/diagnose", response_model=AgentDiagnoseResponse)
def diagnose(
    payload: AgentDiagnoseRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AgentDiagnoseResponse:
    campaign = get_campaign_or_none(db, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    _enforce_demo_rate_limit(user, request)
    return agent.diagnose(
        db,
        campaign,
        payload.query,
        user_id=user.id,
        request_id=request.headers.get("x-request-id"),
        persist=user.role != DEMO_VIEWER_ROLE,
    )


@router.post("/validate-vast", response_model=VastValidationResponse)
def validate_vast_endpoint(
    request: VastValidationRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> VastValidationResponse:
    if not request.creative_id and not request.vast_url:
        raise HTTPException(status_code=422, detail="creative_id or vast_url is required")
    return validate_vast(db, request.creative_id, request.vast_url)


@router.post("/generate-client-summary", response_model=ClientSummaryResponse)
def generate_client_summary(
    payload: ClientSummaryRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ClientSummaryResponse:
    campaign = get_campaign_or_none(db, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    _enforce_demo_rate_limit(user, request)
    return ClientSummaryResponse(
        campaign_id=campaign.id,
        summary=agent.client_safe_summary(
            db,
            campaign,
            payload.diagnosis,
            user_id=user.id,
            request_id=request.headers.get("x-request-id"),
            persist=user.role != DEMO_VIEWER_ROLE,
        ),
        omitted_internal_details=["bid loss reason details", "publisher floor pricing", "raw validation trace"],
    )


@router.get("/tools", response_model=list[ToolDescriptorRead])
def list_agent_tools(_: User = Depends(get_current_user)) -> list[ToolDescriptorRead]:
    """Read-only registry of the bounded tools available to the diagnosis agent.

    Described in an MCP-compatible shape (name, description, input schema, output
    contract) so the tool surface is inspectable without a running MCP server.
    """
    return [ToolDescriptorRead(**descriptor.__dict__) for descriptor in list_tools()]


@router.get("/audit-logs", response_model=list[AuditLogRead])
def audit_logs(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "adops_manager", "product_manager", DEMO_VIEWER_ROLE)),
) -> list[AuditLogRead]:
    logs = list(db.execute(select(AgentAuditLog).order_by(AgentAuditLog.created_at.desc()).limit(100)).scalars())
    return [
        AuditLogRead(
            id=log.id,
            campaign_id=log.campaign_id,
            user_query=log.user_query,
            tools_called=parse_json(log.tools_called, []),
            evidence=parse_json(log.evidence, {}).get("evidence", []),
            diagnosis=log.diagnosis,
            confidence_score=log.confidence_score,
            query_intent=log.query_intent,
            execution_mode=log.execution_mode,
            model_name=log.model_name,
            latency_ms=log.latency_ms,
            request_id=log.request_id,
            created_at=log.created_at,
        )
        for log in logs
    ]
