from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Recommendation, User
from app.time_utils import utc_now


class RecommendationAlreadyDecidedError(ValueError):
    pass


def attach_reviewer_identity(db: Session, recommendations: list[Recommendation]) -> list[Recommendation]:
    """Set transient decided_by_name/decided_by_role attributes for display.

    These are not database columns; they are resolved here so the Governance
    Record can show a real reviewer name/role instead of a raw user id.
    """
    user_ids = {r.decided_by_user_id for r in recommendations if r.decided_by_user_id is not None}
    users_by_id = {}
    if user_ids:
        users_by_id = {u.id: u for u in db.execute(select(User).where(User.id.in_(user_ids))).scalars()}
    for recommendation in recommendations:
        user = users_by_id.get(recommendation.decided_by_user_id)
        recommendation.decided_by_name = user.full_name if user else None
        recommendation.decided_by_role = user.role if user else None
    return recommendations


def list_recommendations(db: Session, campaign_id: Optional[int] = None) -> list[Recommendation]:
    query = select(Recommendation).order_by(Recommendation.created_at.desc())
    if campaign_id is not None:
        query = query.where(Recommendation.campaign_id == campaign_id)
    recommendations = list(db.execute(query).scalars())
    return attach_reviewer_identity(db, recommendations)


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
    attach_reviewer_identity(db, [recommendation])
    return recommendation
