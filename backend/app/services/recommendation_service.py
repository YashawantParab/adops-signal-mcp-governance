from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Recommendation
from app.time_utils import utc_now


class RecommendationAlreadyDecidedError(ValueError):
    pass


def list_recommendations(db: Session, campaign_id: Optional[int] = None) -> list[Recommendation]:
    query = select(Recommendation).order_by(Recommendation.created_at.desc())
    if campaign_id is not None:
        query = query.where(Recommendation.campaign_id == campaign_id)
    return list(db.execute(query).scalars())


def create_recommendation(
    db: Session,
    campaign_id: int,
    title: str,
    description: str,
    expected_impact: str,
    risk_level: str,
) -> Recommendation:
    existing = db.execute(
        select(Recommendation)
        .where(
            Recommendation.campaign_id == campaign_id,
            Recommendation.title == title,
        )
        .order_by(Recommendation.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if existing:
        existing.description = description
        existing.expected_impact = expected_impact
        existing.risk_level = risk_level
        return existing
    recommendation = Recommendation(
        campaign_id=campaign_id,
        title=title,
        description=description,
        expected_impact=expected_impact,
        risk_level=risk_level,
        status="pending",
        created_at=utc_now(),
    )
    db.add(recommendation)
    db.flush()
    return recommendation


def update_recommendation_status(
    db: Session,
    recommendation_id: int,
    status: str,
    *,
    user_id: int,
    reason: str,
) -> Optional[Recommendation]:
    recommendation = db.get(Recommendation, recommendation_id)
    if not recommendation:
        return None
    if recommendation.status != "pending":
        raise RecommendationAlreadyDecidedError(
            f"Recommendation {recommendation_id} is already {recommendation.status}"
        )
    recommendation.status = status
    recommendation.decision_reason = reason.strip()
    recommendation.decided_at = utc_now()
    recommendation.decided_by_user_id = user_id
    db.add(recommendation)
    db.commit()
    db.refresh(recommendation)
    return recommendation
