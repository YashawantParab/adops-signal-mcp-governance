from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from typing import Optional

from app.models import (
    BidResponse,
    Campaign,
    Creative,
    InventorySegment,
    PacingSnapshot,
    VastValidationError,
)
from app.schemas import BidSummary, CampaignDetail, CampaignHealth, CampaignRead, CampaignSummary, InventorySummary
from app.services.json_fields import parse_list


def campaign_to_read(campaign: Campaign) -> CampaignRead:
    return CampaignRead(
        id=campaign.id,
        advertiser_id=campaign.advertiser_id,
        advertiser_name=campaign.advertiser.name if campaign.advertiser else None,
        campaign_name=campaign.campaign_name,
        campaign_type=campaign.campaign_type,
        start_date=campaign.start_date,
        end_date=campaign.end_date,
        goal_impressions=campaign.goal_impressions,
        delivered_impressions=campaign.delivered_impressions,
        budget=float(campaign.budget),
        status=campaign.status,
        target_countries=parse_list(campaign.target_countries),
        target_devices=parse_list(campaign.target_devices),
        target_content_categories=parse_list(campaign.target_content_categories),
        frequency_cap=campaign.frequency_cap,
        bid_floor=float(campaign.bid_floor),
        priority_level=campaign.priority_level,
    )


def get_campaign_or_none(db: Session, campaign_id: int) -> Optional[Campaign]:
    return db.execute(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .options(selectinload(Campaign.advertiser), selectinload(Campaign.creatives))
    ).scalar_one_or_none()


def latest_pacing(db: Session, campaign_id: int) -> Optional[PacingSnapshot]:
    return db.execute(
        select(PacingSnapshot)
        .where(PacingSnapshot.campaign_id == campaign_id)
        .order_by(PacingSnapshot.snapshot_date.desc())
        .limit(1)
    ).scalar_one_or_none()


def inventory_summary(db: Session, campaign: Campaign) -> InventorySummary:
    countries = parse_list(campaign.target_countries)
    devices = parse_list(campaign.target_devices)
    categories = parse_list(campaign.target_content_categories)

    segments = list(db.execute(select(InventorySegment)).scalars())
    total = sum(segment.avg_daily_available_impressions for segment in segments)
    eligible = [
        segment
        for segment in segments
        if segment.country in countries and segment.device_type in devices and segment.content_category in categories
    ]
    eligible_total = sum(segment.avg_daily_available_impressions for segment in eligible)
    pct = round((eligible_total / total) * 100, 1) if total else 0.0

    constrained: list[str] = []
    if len(countries) == 1:
        constrained.append("country")
    if len(devices) == 1:
        constrained.append("device")
    if len(categories) <= 2:
        constrained.append("content category")
    if eligible_total < max(campaign.goal_impressions // 12, 40_000):
        constrained.append("available impressions")

    return InventorySummary(
        eligible_segments=len(eligible),
        eligible_daily_impressions=eligible_total,
        total_daily_impressions=total,
        eligible_inventory_percentage=pct,
        constrained_dimensions=constrained,
    )


def bid_summary(db: Session, campaign_id: int) -> BidSummary:
    bids = list(db.execute(select(BidResponse).where(BidResponse.campaign_id == campaign_id)).scalars())
    if not bids:
        return BidSummary(total_bids=0, win_rate=0, below_floor_rate=0, avg_bid_price=0, avg_floor_price=0)

    won = sum(1 for bid in bids if bid.won)
    below_floor = sum(1 for bid in bids if float(bid.bid_price) < float(bid.floor_price))
    avg_bid = sum(float(bid.bid_price) for bid in bids) / len(bids)
    avg_floor = sum(float(bid.floor_price) for bid in bids) / len(bids)
    return BidSummary(
        total_bids=len(bids),
        win_rate=round((won / len(bids)) * 100, 1),
        below_floor_rate=round((below_floor / len(bids)) * 100, 1),
        avg_bid_price=round(avg_bid, 2),
        avg_floor_price=round(avg_floor, 2),
    )


def creative_status(db: Session, campaign_id: int) -> tuple[str, int]:
    creatives = list(db.execute(select(Creative).where(Creative.campaign_id == campaign_id)).scalars())
    errors = db.scalar(
        select(func.count(VastValidationError.id))
        .join(Creative, Creative.id == VastValidationError.creative_id)
        .where(Creative.campaign_id == campaign_id)
    ) or 0
    if any(creative.approval_status == "rejected" for creative in creatives):
        return "rejected", int(errors)
    if errors:
        return "errors_detected", int(errors)
    if all(creative.approval_status == "approved" for creative in creatives):
        return "approved", int(errors)
    return "pending_review", int(errors)


def main_issue(health: CampaignHealth, campaign: Campaign) -> str:
    if health.creative_status == "rejected":
        return "Creative rejected"
    if health.inventory.eligible_inventory_percentage < 25:
        return "Eligible inventory too narrow"
    if health.vast_error_count > 0:
        return "VAST validation errors"
    if health.bid_analysis.below_floor_rate > 45:
        return "Bid price below publisher floors"
    if campaign.frequency_cap <= 1:
        return "Frequency cap too strict"
    if health.pacing_percentage < 80:
        return "Behind pacing"
    return "Healthy"


def get_campaign_health(db: Session, campaign: Campaign) -> CampaignHealth:
    pacing = latest_pacing(db, campaign.id)
    inventory = inventory_summary(db, campaign)
    bids = bid_summary(db, campaign.id)
    status, error_count = creative_status(db, campaign.id)
    health = CampaignHealth(
        campaign_id=campaign.id,
        pacing_percentage=round(pacing.pacing_percentage if pacing else 0, 1),
        expected_delivery=pacing.expected_delivery if pacing else 0,
        actual_delivery=pacing.actual_delivery if pacing else campaign.delivered_impressions,
        risk_level=pacing.risk_level if pacing else "Unknown",
        creative_status=status,
        vast_error_count=error_count,
        inventory=inventory,
        bid_analysis=bids,
        main_suspected_issue="",
    )
    health.main_suspected_issue = main_issue(health, campaign)
    return health


def list_campaign_summaries(db: Session) -> list[CampaignSummary]:
    campaigns = list(
        db.execute(select(Campaign).options(selectinload(Campaign.advertiser)).order_by(Campaign.id)).scalars()
    )
    summaries: list[CampaignSummary] = []
    for campaign in campaigns:
        health = get_campaign_health(db, campaign)
        base = campaign_to_read(campaign).model_dump()
        summaries.append(
            CampaignSummary(
                **base,
                pacing_percentage=health.pacing_percentage,
                risk_level=health.risk_level,
                main_issue=health.main_suspected_issue,
                creative_status=health.creative_status,
            )
        )
    return summaries


def get_campaign_detail(db: Session, campaign: Campaign) -> CampaignDetail:
    health = get_campaign_health(db, campaign)
    vast_errors = list(
        db.execute(
            select(VastValidationError)
            .join(Creative, Creative.id == VastValidationError.creative_id)
            .where(Creative.campaign_id == campaign.id)
            .order_by(VastValidationError.detected_at.desc())
        ).scalars()
    )
    pacing_history = [
        {
            "date": snapshot.snapshot_date.isoformat(),
            "expected_delivery": snapshot.expected_delivery,
            "actual_delivery": snapshot.actual_delivery,
            "pacing_percentage": snapshot.pacing_percentage,
            "risk_level": snapshot.risk_level,
        }
        for snapshot in db.execute(
            select(PacingSnapshot).where(PacingSnapshot.campaign_id == campaign.id).order_by(PacingSnapshot.snapshot_date)
        ).scalars()
    ]
    return CampaignDetail(
        **campaign_to_read(campaign).model_dump(),
        health=health,
        creatives=campaign.creatives,
        vast_errors=vast_errors,
        pacing_history=pacing_history,
    )
