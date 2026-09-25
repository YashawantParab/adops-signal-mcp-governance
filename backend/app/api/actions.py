from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import ActionExecution, ProposedAction, User
from app.schemas import (
    ActionDecisionRequest,
    ActionExecutionRead,
    ProposeActionRequest,
    ProposedActionRead,
)
from app.security import DEMO_VIEWER_ROLE, require_roles
from app.services.action_execution_service import (
    ActionError,
    approve_action,
    execute_action,
    propose_action,
    rollback_action,
)

router = APIRouter(prefix="/api/actions", tags=["actions"])

_READ_ROLES = ("admin", "adops_manager", "product_manager", DEMO_VIEWER_ROLE)
_WRITE_ROLES = ("admin", "adops_manager", "product_manager")
_DECISION_ROLES = ("admin", "adops_manager")


def _to_read(action: ProposedAction) -> ProposedActionRead:
    return ProposedActionRead(
        id=action.id,
        campaign_id=action.campaign_id,
        campaign_name=action.campaign.campaign_name if action.campaign else None,
        agent_run_id=action.agent_run_id,
        approval_request_id=action.approval_request_id,
        action_type=action.action_type,
        requested_params=action.requested_params,
        risk_class=action.risk_class,
        status=action.status,
        proposed_by=action.proposed_by,
        created_at=action.created_at,
        updated_at=action.updated_at,
        approval_status=action.approval_request.status if action.approval_request else None,
        executions=[ActionExecutionRead.model_validate(item) for item in action.executions],
    )


def _load(db: Session, action_id: int) -> ProposedAction | None:
    return db.execute(
        select(ProposedAction)
        .where(ProposedAction.id == action_id)
        .options(
            selectinload(ProposedAction.campaign),
            selectinload(ProposedAction.approval_request),
            selectinload(ProposedAction.executions).selectinload(ActionExecution.verifications),
            selectinload(ProposedAction.executions).selectinload(ActionExecution.rollbacks),
        )
    ).scalar_one_or_none()


@router.get("", response_model=list[ProposedActionRead])
def list_actions(
    db: Session = Depends(get_db), _: User = Depends(require_roles(*_READ_ROLES))
) -> list[ProposedActionRead]:
    actions = list(
        db.execute(
            select(ProposedAction)
            .options(
                selectinload(ProposedAction.campaign),
                selectinload(ProposedAction.approval_request),
                selectinload(ProposedAction.executions).selectinload(ActionExecution.verifications),
                selectinload(ProposedAction.executions).selectinload(ActionExecution.rollbacks),
            )
            .order_by(ProposedAction.created_at.desc(), ProposedAction.id.desc())
            .limit(100)
        ).scalars()
    )
    return [_to_read(action) for action in actions]


@router.get("/{action_id}", response_model=ProposedActionRead)
def get_action(
    action_id: int, db: Session = Depends(get_db), _: User = Depends(require_roles(*_READ_ROLES))
) -> ProposedActionRead:
    action = _load(db, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Proposed action not found")
    return _to_read(action)


@router.post("/propose", response_model=ProposedActionRead)
def propose(
    payload: ProposeActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*_WRITE_ROLES)),
) -> ProposedActionRead:
    try:
        action = propose_action(
            db, campaign_id=payload.campaign_id, action_type=payload.action_type,
            requested_params=payload.requested_params, proposed_by=user.email,
        )
    except ActionError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc
    return _to_read(_load(db, action.id))


@router.post("/{action_id}/approve", response_model=ProposedActionRead)
def approve(
    action_id: int, payload: ActionDecisionRequest,
    db: Session = Depends(get_db), user: User = Depends(require_roles(*_DECISION_ROLES)),
) -> ProposedActionRead:
    try:
        approve_action(db, action_id, reviewer=user, rationale=payload.rationale)
    except ActionError as exc:
        status_code = 404 if exc.code == "ACTION_NOT_FOUND" else 409 if exc.code == "INVALID_STATE" else 422
        raise HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    return _to_read(_load(db, action_id))


@router.post("/{action_id}/execute", response_model=ProposedActionRead)
def execute(
    action_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*_DECISION_ROLES))
) -> ProposedActionRead:
    try:
        execute_action(db, action_id, executor=user)
    except ActionError as exc:
        status_code = 404 if exc.code == "ACTION_NOT_FOUND" else 409
        raise HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    return _to_read(_load(db, action_id))


@router.post("/{action_id}/rollback", response_model=ProposedActionRead)
def rollback(
    action_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*_DECISION_ROLES))
) -> ProposedActionRead:
    action = _load(db, action_id)
    if not action or not action.executions:
        raise HTTPException(status_code=404, detail="No execution found for this action")
    latest_execution = action.executions[-1]
    try:
        rollback_action(db, latest_execution.id, actor=user)
    except ActionError as exc:
        status_code = 404 if exc.code == "EXECUTION_NOT_FOUND" else 409
        raise HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    return _to_read(_load(db, action_id))
