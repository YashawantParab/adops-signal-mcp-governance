from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import CampaignDetail, CampaignHealth, CampaignSummary
from app.models import User
from app.security import get_current_user
from app.services.campaign_service import get_campaign_detail, get_campaign_health, get_campaign_or_none, list_campaign_summaries

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


@router.get("", response_model=list[CampaignSummary])
def list_campaigns(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[CampaignSummary]:
    return list_campaign_summaries(db)


@router.get("/{campaign_id}", response_model=CampaignDetail)
def get_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CampaignDetail:
    campaign = get_campaign_or_none(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return get_campaign_detail(db, campaign)


@router.get("/{campaign_id}/health", response_model=CampaignHealth)
def campaign_health(
    campaign_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CampaignHealth:
    campaign = get_campaign_or_none(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return get_campaign_health(db, campaign)
