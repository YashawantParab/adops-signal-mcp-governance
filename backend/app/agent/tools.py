from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AdRequest, BidResponse, Campaign, Creative, Impression, VastValidationError
from app.schemas import EvidenceItem
from app.services import campaign_service
from app.services.rag_service import retrieve


@dataclass(frozen=True)
class ToolResult:
    name: str
    evidence: list[EvidenceItem]
    payload: dict


def check_pacing(db: Session, campaign: Campaign) -> ToolResult:
    health = campaign_service.get_campaign_health(db, campaign)
    message = (
        f"Latest pacing is {health.pacing_percentage}% with {health.actual_delivery:,} delivered "
        f"against {health.expected_delivery:,} expected."
    )
    return ToolResult(
        name="campaign_pacing_tool",
        evidence=[EvidenceItem(source="pacing_snapshots", message=message, metric=f"{health.pacing_percentage}%")],
        payload=health.model_dump(),
    )


def analyze_targeting(db: Session, campaign: Campaign) -> ToolResult:
    inventory = campaign_service.inventory_summary(db, campaign)
    dimensions = ", ".join(inventory.constrained_dimensions) or "none"
    message = (
        f"Eligible inventory is {inventory.eligible_inventory_percentage}% of modeled supply "
        f"across {inventory.eligible_segments} matching segments; constrained dimensions: {dimensions}."
    )
    return ToolResult(
        name="targeting_analyzer_tool",
        evidence=[EvidenceItem(source="inventory_segments", message=message, metric=f"{inventory.eligible_inventory_percentage}%")],
        payload=inventory.model_dump(),
    )


def check_inventory(db: Session, campaign: Campaign) -> ToolResult:
    requests = db.scalar(select(func.count(AdRequest.id)).where(AdRequest.campaign_id == campaign.id)) or 0
    failed = (
        db.scalar(
            select(func.count(AdRequest.id)).where(
                AdRequest.campaign_id == campaign.id,
                AdRequest.request_status == "failed",
            )
        )
        or 0
    )
    top_failure = db.execute(
        select(AdRequest.failure_reason, func.count(AdRequest.id))
        .where(AdRequest.campaign_id == campaign.id, AdRequest.failure_reason.is_not(None))
        .group_by(AdRequest.failure_reason)
        .order_by(func.count(AdRequest.id).desc())
        .limit(1)
    ).first()
    failure_rows = db.execute(
        select(AdRequest.failure_reason, func.count(AdRequest.id))
        .where(AdRequest.campaign_id == campaign.id, AdRequest.failure_reason.is_not(None))
        .group_by(AdRequest.failure_reason)
        .order_by(func.count(AdRequest.id).desc())
    ).all()
    failure_reasons = {str(reason): int(count) for reason, count in failure_rows}
    failure_rate = round((failed / requests) * 100, 1) if requests else 0.0
    reason = top_failure[0] if top_failure else "no dominant failure reason"
    return ToolResult(
        name="inventory_checker_tool",
        evidence=[
            EvidenceItem(
                source="ad_requests",
                message=f"{failure_rate}% of campaign ad requests failed; dominant reason: {reason}.",
                metric=f"{failed}/{requests}",
            ),
            EvidenceItem(
                source="ad_requests",
                message=(
                    "Failure reason distribution: "
                    + ", ".join(f"{key}={value}" for key, value in failure_reasons.items())
                    if failure_reasons
                    else "No request failure reasons were recorded."
                ),
            ),
        ],
        payload={
            "request_count": requests,
            "failed_count": failed,
            "failure_rate": failure_rate,
            "top_failure_reason": reason,
            "failure_reasons": failure_reasons,
        },
    )


def check_portfolio_pressure(db: Session, campaign: Campaign) -> ToolResult:
    shared_reason = "shared_inventory_consumed_by_high_priority_campaign"
    affected_count = (
        db.scalar(
            select(func.count(AdRequest.id)).where(
                AdRequest.campaign_id == campaign.id,
                AdRequest.failure_reason == shared_reason,
            )
        )
        or 0
    )
    portfolio_count = (
        db.scalar(
            select(func.count(AdRequest.id)).where(
                AdRequest.campaign_id != campaign.id,
                AdRequest.failure_reason == shared_reason,
            )
        )
        or 0
    )
    high_priority_campaigns = list(
        db.execute(select(Campaign).where(Campaign.priority_level == "High")).scalars()
    )
    high_priority_ids = [item.id for item in high_priority_campaigns]
    if campaign.priority_level == "High":
        message = (
            f"Campaign {campaign.id} is high priority; {portfolio_count} failed requests on other campaigns "
            "are labeled as shared inventory consumed by a high-priority campaign."
        )
    else:
        message = (
            f"{affected_count} requests for campaign {campaign.id} were blocked by shared high-priority "
            f"inventory pressure; active high-priority campaigns: {high_priority_ids or 'none'}."
        )
    return ToolResult(
        name="portfolio_inventory_pressure_tool",
        evidence=[EvidenceItem(source="ad_requests,campaigns", message=message, metric=str(affected_count))],
        payload={
            "affected_request_count": int(affected_count),
            "portfolio_affected_request_count": int(portfolio_count),
            "high_priority_campaign_ids": high_priority_ids,
            "campaign_is_high_priority": campaign.priority_level == "High",
        },
    )


def validate_creatives(db: Session, campaign: Campaign) -> ToolResult:
    creatives = list(db.execute(select(Creative).where(Creative.campaign_id == campaign.id)).scalars())
    errors = list(
        db.execute(
            select(VastValidationError)
            .join(Creative, Creative.id == VastValidationError.creative_id)
            .where(Creative.campaign_id == campaign.id)
        ).scalars()
    )
    rejected = [creative for creative in creatives if creative.approval_status == "rejected"]
    message = (
        f"{len(rejected)} rejected creative(s), {len(errors)} VAST validation error(s), "
        f"{len(creatives)} total creative(s)."
    )
    return ToolResult(
        name="vast_validation_tool",
        evidence=[EvidenceItem(source="creatives,vast_validation_errors", message=message, metric=str(len(errors)))],
        payload={
            "creative_count": len(creatives),
            "rejected_count": len(rejected),
            "error_count": len(errors),
            "error_codes": sorted({error.error_code for error in errors}),
            "rejection_reasons": [creative.rejection_reason for creative in rejected if creative.rejection_reason],
        },
    )


def analyze_bids(db: Session, campaign: Campaign) -> ToolResult:
    bids = campaign_service.bid_summary(db, campaign.id)
    message = (
        f"Bid win rate is {bids.win_rate}% and {bids.below_floor_rate}% of bids are below publisher floors. "
        f"Average bid: EUR {bids.avg_bid_price}; average floor: EUR {bids.avg_floor_price}."
    )
    return ToolResult(
        name="sql_analysis_tool",
        evidence=[EvidenceItem(source="bid_responses", message=message, metric=f"{bids.below_floor_rate}% below floor")],
        payload=bids.model_dump(),
    )


def check_frequency_and_dates(db: Session, campaign: Campaign) -> ToolResult:
    first_impression = db.scalar(
        select(func.min(Impression.timestamp)).where(Impression.campaign_id == campaign.id)
    )
    is_recent_launch = campaign.start_date >= date(2026, 6, 16)
    launch_lag_days = (first_impression.date() - campaign.start_date).days if first_impression and is_recent_launch else None
    message = f"Frequency cap is {campaign.frequency_cap} per household/day."
    if launch_lag_days and launch_lag_days > 1:
        message += f" First impression appeared {launch_lag_days} days after campaign start."
    return ToolResult(
        name="campaign_setup_tool",
        evidence=[EvidenceItem(source="campaigns,impressions", message=message, metric=str(campaign.frequency_cap))],
        payload={"frequency_cap": campaign.frequency_cap, "launch_lag_days": launch_lag_days},
    )


def retrieve_docs(db: Session, query: str) -> ToolResult:
    docs = retrieve(db, query)
    if docs:
        message = "Retrieved " + ", ".join(doc.source for doc in docs)
    else:
        message = "No matching operational documentation found."
    evidence = [EvidenceItem(source="adops_docs", message=message)]
    evidence.extend(
        EvidenceItem(
            source=f"adops_docs:{doc.source}",
            message=f"{doc.title}: {doc.content[:420]}",
            metric=f"similarity {doc.score:.2f}",
        )
        for doc in docs
    )
    return ToolResult(
        name="rag_documentation_lookup",
        evidence=evidence,
        payload={
            "docs": [
                {"source": doc.source, "title": doc.title, "content": doc.content, "score": doc.score}
                for doc in docs
            ]
        },
    )


def _target_date_from_query(campaign: Campaign, query: str, today: date) -> date:
    normalized = query.lower()
    if "tomorrow" in normalized:
        return min(today + timedelta(days=1), campaign.end_date)
    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    for name, weekday in weekdays.items():
        if name in normalized:
            days_ahead = (weekday - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return min(today + timedelta(days=days_ahead), campaign.end_date)
    return campaign.end_date


def can_hit_goal_by_end(
    campaign: Campaign,
    today: Optional[date] = None,
    target_date: Optional[date] = None,
) -> dict:
    today = today or date(2026, 6, 23)
    target_date = min(target_date or campaign.end_date, campaign.end_date)
    remaining_days = max((target_date - today).days + 1, 0)
    remaining_goal = max(campaign.goal_impressions - campaign.delivered_impressions, 0)
    required_daily = round(remaining_goal / remaining_days) if remaining_days else remaining_goal
    recent_daily = round(campaign.delivered_impressions / max((today - campaign.start_date).days + 1, 1))
    feasible = remaining_days > 0 and required_daily <= recent_daily * 1.35
    projected_total = campaign.delivered_impressions + recent_daily * remaining_days
    return {
        "target_date": target_date.isoformat(),
        "remaining_days": remaining_days,
        "remaining_goal": remaining_goal,
        "required_daily": required_daily,
        "recent_daily": recent_daily,
        "projected_total": projected_total,
        "projected_gap": max(campaign.goal_impressions - projected_total, 0),
        "feasible": feasible,
    }


def forecast_goal_attainment(db: Session, campaign: Campaign, query: str) -> ToolResult:
    del db
    today = date(2026, 6, 23)
    target_date = _target_date_from_query(campaign, query, today)
    forecast = can_hit_goal_by_end(campaign, today=today, target_date=target_date)
    status = "feasible" if forecast["feasible"] else "at risk"
    message = (
        f"Goal attainment is {status} by {forecast['target_date']}: "
        f"{forecast['required_daily']:,} impressions/day are required versus a recent "
        f"{forecast['recent_daily']:,}/day run rate. Projected gap: {forecast['projected_gap']:,} impressions."
    )
    return ToolResult(
        name="goal_feasibility_tool",
        evidence=[
            EvidenceItem(
                source="campaigns,pacing_snapshots",
                message=message,
                metric="Feasible" if forecast["feasible"] else "At risk",
            )
        ],
        payload=forecast,
    )
