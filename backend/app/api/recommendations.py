from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import RecommendationDecisionRequest, RecommendationRead
from app.models import User
from app.security import get_current_user, require_roles
from app.services.recommendation_service import (
    RecommendationAlreadyDecidedError,
    list_recommendations,
    update_recommendation_status,
)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("", response_model=list[RecommendationRead])
def all_recommendations(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[RecommendationRead]:
    return list_recommendations(db)


@router.get("/{campaign_id}", response_model=list[RecommendationRead])
def campaign_recommendations(
    campaign_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[RecommendationRead]:
    return list_recommendations(db, campaign_id)


@router.post("/{recommendation_id}/approve", response_model=RecommendationRead)
def approve_recommendation(
    recommendation_id: int,
    payload: RecommendationDecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "adops_manager")),
) -> RecommendationRead:
    try:
        recommendation = update_recommendation_status(
            db,
            recommendation_id,
            "approved",
            user_id=user.id,
            reason=payload.reason,
        )
    except RecommendationAlreadyDecidedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not recommendation:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return recommendation


@router.post("/{recommendation_id}/reject", response_model=RecommendationRead)
def reject_recommendation(
    recommendation_id: int,
    payload: RecommendationDecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "adops_manager")),
) -> RecommendationRead:
    try:
        recommendation = update_recommendation_status(
            db,
            recommendation_id,
            "rejected",
            user_id=user.id,
            reason=payload.reason,
        )
    except RecommendationAlreadyDecidedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not recommendation:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return recommendation
