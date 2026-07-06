from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import AdOpsSignalAgent
from app.database import get_db
from app.models import AgentAuditLog, User
from app.schemas import (
    AgentDiagnoseRequest,
    AgentDiagnoseResponse,
    AuditLogRead,
    ClientSummaryRequest,
    ClientSummaryResponse,
    VastValidationRequest,
    VastValidationResponse,
)
from app.services.campaign_service import get_campaign_or_none
from app.services.json_fields import parse_json
from app.services.vast_service import validate_vast
from app.security import get_current_user, require_roles

router = APIRouter(prefix="/api/agent", tags=["agent"])
agent = AdOpsSignalAgent()


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
    return agent.diagnose(
        db,
        campaign,
        payload.query,
        user_id=user.id,
        request_id=request.headers.get("x-request-id"),
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
    return ClientSummaryResponse(
        campaign_id=campaign.id,
        summary=agent.client_safe_summary(
            db,
            campaign,
            payload.diagnosis,
            user_id=user.id,
            request_id=request.headers.get("x-request-id"),
        ),
        omitted_internal_details=["bid loss reason details", "publisher floor pricing", "raw validation trace"],
    )


@router.get("/audit-logs", response_model=list[AuditLogRead])
def audit_logs(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "adops_manager", "product_manager")),
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
