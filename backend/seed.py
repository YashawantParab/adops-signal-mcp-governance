from __future__ import annotations

import csv
import json
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable

from sqlalchemy import delete, text

from app.database import SessionLocal, create_all, engine
from app.models import (
    AdRequest,
    Advertiser,
    AgentAuditLog,
    BidResponse,
    Campaign,
    Creative,
    Impression,
    InventorySegment,
    KnowledgeChunk,
    PacingSnapshot,
    Publisher,
    Recommendation,
    User,
    VastValidationError,
)
from app.config import get_settings
from app.security import hash_password
from app.services.json_fields import dump_list
from app.time_utils import utc_now

RANDOM_SEED = 1045
TODAY = date(2026, 6, 23)
DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def to_row(obj) -> dict:
    row = {}
    for column in obj.__table__.columns:
        value = getattr(obj, column.name)
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        row[column.name] = value
    return row


def write_csv(filename: str, rows: Iterable[object]) -> None:
    rows = list(rows)
    if not rows:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / filename
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(to_row(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(to_row(row))


def risk_for_pacing(value: float) -> str:
    if value < 65:
        return "High"
    if value < 85:
        return "Medium"
    return "Low"


def build_seed_data() -> dict[str, list]:
    random.seed(RANDOM_SEED)
    settings = get_settings()
    users = [
        User(
            id=1,
            email=settings.demo_admin_email.lower(),
            full_name="Maya Hoffmann",
            password_hash=hash_password(settings.demo_admin_password, b"adops-signal-1"),
            role="adops_manager",
            is_active=True,
        ),
        User(
            id=2,
            email="product@demo.adops.local",
            full_name="Sofia Anders",
            password_hash=hash_password("ProductDemo!2026", b"adops-signal-2"),
            role="product_manager",
            is_active=True,
        ),
        User(
            id=3,
            email="success@demo.adops.local",
            full_name="Ravi Menon",
            password_hash=hash_password("SuccessDemo!2026", b"adops-signal-3"),
            role="viewer",
            is_active=True,
        ),
        User(
            id=4,
            email="campaignops@demo.adops.local",
            full_name="Daniel Keller",
            password_hash=hash_password("OpsManager!2026", b"adops-signal-4"),
            role="adops_manager",
            is_active=True,
        ),
    ]
    advertisers = [
        Advertiser(id=201, name="RheinAuto Mobility", industry="Automotive", region="DACH"),
        Advertiser(id=202, name="NordicStream+", industry="Streaming", region="Nordics"),
        Advertiser(id=203, name="LuxeHome Retail", industry="Retail", region="Europe"),
        Advertiser(id=204, name="GameHub Studios", industry="Gaming", region="Europe"),
        Advertiser(id=205, name="Meridian Capital Partners", industry="Finance", region="Europe"),
        Advertiser(id=206, name="Solstice Mobile", industry="Telecom", region="DACH"),
        Advertiser(id=207, name="Vantage Travel Group", industry="Travel", region="Europe"),
    ]
    publishers = [
        Publisher(id=301, name="Premium CTV Exchange", country="DE", inventory_type="CTV", device_types=dump_list(["CTV", "HbbTV"])),
        Publisher(id=302, name="Addressable TV Network", country="AT", inventory_type="Addressable TV", device_types=dump_list(["HbbTV", "SetTopBox"])),
        Publisher(id=303, name="Broadcaster Video Hub", country="SE", inventory_type="Video", device_types=dump_list(["CTV", "Mobile", "Desktop"])),
        Publisher(id=304, name="Local Streaming Marketplace", country="NL", inventory_type="Streaming", device_types=dump_list(["CTV", "Desktop"])),
        Publisher(id=305, name="Programmatic Video Supply", country="DE", inventory_type="Programmatic Video", device_types=dump_list(["Desktop", "CTV"])),
        Publisher(id=306, name="Sports Streaming Network", country="UK", inventory_type="Sports Streaming", device_types=dump_list(["CTV"])),
    ]
    inventory_segments = [
        InventorySegment(id=401, publisher_id=301, segment_name="DE CTV Sports Prime", country="DE", device_type="CTV", content_category="Sports", avg_daily_available_impressions=145_000, floor_price=18.0),
        InventorySegment(id=402, publisher_id=301, segment_name="DE CTV Entertainment", country="DE", device_type="CTV", content_category="Entertainment", avg_daily_available_impressions=210_000, floor_price=16.5),
        InventorySegment(id=403, publisher_id=301, segment_name="DE HbbTV News", country="DE", device_type="HbbTV", content_category="News", avg_daily_available_impressions=95_000, floor_price=14.0),
        InventorySegment(id=404, publisher_id=302, segment_name="AT HbbTV Entertainment", country="AT", device_type="HbbTV", content_category="Entertainment", avg_daily_available_impressions=54_000, floor_price=15.5),
        InventorySegment(id=405, publisher_id=302, segment_name="AT SetTopBox Lifestyle", country="AT", device_type="SetTopBox", content_category="Lifestyle", avg_daily_available_impressions=36_000, floor_price=12.5),
        InventorySegment(id=406, publisher_id=303, segment_name="SE CTV Entertainment", country="SE", device_type="CTV", content_category="Entertainment", avg_daily_available_impressions=118_000, floor_price=17.0),
        InventorySegment(id=407, publisher_id=303, segment_name="SE Mobile Gaming", country="SE", device_type="Mobile", content_category="Gaming", avg_daily_available_impressions=180_000, floor_price=9.5),
        InventorySegment(id=408, publisher_id=303, segment_name="NO CTV News", country="NO", device_type="CTV", content_category="News", avg_daily_available_impressions=42_000, floor_price=18.5),
        InventorySegment(id=409, publisher_id=301, segment_name="DE Desktop Finance Video", country="DE", device_type="Desktop", content_category="Finance", avg_daily_available_impressions=65_000, floor_price=11.0),
        InventorySegment(id=410, publisher_id=302, segment_name="CH HbbTV Sports", country="CH", device_type="HbbTV", content_category="Sports", avg_daily_available_impressions=28_000, floor_price=19.0),
        InventorySegment(id=411, publisher_id=305, segment_name="DE Programmatic Finance Video", country="DE", device_type="Desktop", content_category="Finance", avg_daily_available_impressions=38_000, floor_price=20.0),
        InventorySegment(id=412, publisher_id=305, segment_name="NL Programmatic Business News", country="NL", device_type="CTV", content_category="Business News", avg_daily_available_impressions=22_000, floor_price=21.5),
        InventorySegment(id=413, publisher_id=306, segment_name="UK Weekend Sports Streaming", country="UK", device_type="CTV", content_category="Sports", avg_daily_available_impressions=160_000, floor_price=16.0),
        InventorySegment(id=414, publisher_id=306, segment_name="UK Weekday Travel Streaming", country="UK", device_type="CTV", content_category="Travel", avg_daily_available_impressions=24_000, floor_price=15.0),
    ]
    campaigns = [
        Campaign(
            id=1045,
            advertiser_id=201,
            campaign_name="RheinAuto CTV Launch",
            campaign_type="CTV Awareness",
            start_date=date(2026, 6, 10),
            end_date=date(2026, 6, 27),
            goal_impressions=1_000_000,
            delivered_impressions=238_000,
            budget=95_000,
            status="active",
            target_countries=dump_list(["DE", "AT"]),
            target_devices=dump_list(["CTV"]),
            target_content_categories=dump_list(["Sports"]),
            frequency_cap=2,
            bid_floor=15.0,
            priority_level="Standard",
        ),
        Campaign(
            id=1046,
            advertiser_id=202,
            campaign_name="NordicStream Family Addressable",
            campaign_type="Addressable TV",
            start_date=date(2026, 6, 13),
            end_date=date(2026, 6, 30),
            goal_impressions=650_000,
            delivered_impressions=96_000,
            budget=62_000,
            status="active",
            target_countries=dump_list(["AT"]),
            target_devices=dump_list(["HbbTV"]),
            target_content_categories=dump_list(["Entertainment"]),
            frequency_cap=1,
            bid_floor=14.5,
            priority_level="Standard",
        ),
        Campaign(
            id=1047,
            advertiser_id=203,
            campaign_name="LuxeHome Premium Video",
            campaign_type="Online Video",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 28),
            goal_impressions=800_000,
            delivered_impressions=515_000,
            budget=58_000,
            status="active",
            target_countries=dump_list(["DE"]),
            target_devices=dump_list(["Desktop", "Mobile"]),
            target_content_categories=dump_list(["Lifestyle", "Finance"]),
            frequency_cap=4,
            bid_floor=10.5,
            priority_level="Low",
        ),
        Campaign(
            id=1048,
            advertiser_id=204,
            campaign_name="GameHub Studios Nordic CTV Launch",
            campaign_type="CTV Launch",
            start_date=date(2026, 6, 18),
            end_date=date(2026, 6, 26),
            goal_impressions=450_000,
            delivered_impressions=54_000,
            budget=44_000,
            status="active",
            target_countries=dump_list(["SE", "NO"]),
            target_devices=dump_list(["CTV"]),
            target_content_categories=dump_list(["Gaming", "Entertainment"]),
            frequency_cap=3,
            bid_floor=13.0,
            priority_level="Standard",
        ),
        Campaign(
            id=1049,
            advertiser_id=206,
            campaign_name="Solstice Mobile 5G Flagship Sponsorship",
            campaign_type="CTV Sponsorship",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 25),
            goal_impressions=1_200_000,
            delivered_impressions=1_050_000,
            budget=160_000,
            status="active",
            target_countries=dump_list(["DE"]),
            target_devices=dump_list(["CTV", "HbbTV"]),
            target_content_categories=dump_list(["Sports", "Entertainment", "News"]),
            frequency_cap=6,
            bid_floor=19.0,
            priority_level="High",
        ),
        Campaign(
            id=1050,
            advertiser_id=205,
            campaign_name="Meridian Capital Partners Wealth Management Premium Video",
            campaign_type="Premium Video",
            start_date=date(2026, 6, 5),
            end_date=date(2026, 6, 30),
            goal_impressions=900_000,
            delivered_impressions=430_000,
            budget=110_000,
            status="active",
            target_countries=dump_list(["DE", "NL"]),
            target_devices=dump_list(["Desktop", "CTV"]),
            target_content_categories=dump_list(["Finance", "Business News"]),
            frequency_cap=3,
            bid_floor=20.0,
            priority_level="Standard",
        ),
        Campaign(
            id=1051,
            advertiser_id=207,
            campaign_name="Vantage Travel Group Getaway Season Launch",
            campaign_type="CTV Awareness",
            start_date=date(2026, 6, 16),
            end_date=date(2026, 7, 5),
            goal_impressions=550_000,
            delivered_impressions=140_000,
            budget=72_000,
            status="active",
            target_countries=dump_list(["UK"]),
            target_devices=dump_list(["CTV"]),
            target_content_categories=dump_list(["Travel", "Sports"]),
            frequency_cap=3,
            bid_floor=15.5,
            priority_level="Standard",
        ),
    ]

    creatives: list[Creative] = []
    creative_id = 501
    for campaign in campaigns:
        for variant in range(4):
            rejected = campaign.id == 1046 and variant == 1
            creative = Creative(
                id=creative_id,
                campaign_id=campaign.id,
                creative_name=f"{campaign.campaign_name} {15 + variant * 5}s V{variant + 1}",
                format="VAST",
                duration_seconds=15 + variant * 5,
                vast_url=f"https://ads.example.test/vast/{campaign.id}/{variant + 1}",
                approval_status="rejected" if rejected else "approved",
                rejection_reason="Missing companion asset for addressable TV placement." if rejected else None,
                last_validated_at=datetime.combine(TODAY - timedelta(days=variant), time(hour=9 + variant)),
            )
            creatives.append(creative)
            creative_id += 1

    errors: list[VastValidationError] = []
    error_specs = [
        (506, "COMPANION_MISSING", "Required companion asset is missing from the creative package.", "high", 4),
        (501, "VAST_TIMEOUT", "VAST wrapper chain exceeded timeout threshold.", "medium", 5),
        (505, "VAST_TIMEOUT", "Media file host responded too slowly for CTV playback.", "high", 4),
        (513, "MEDIAFILE_MISSING", "No compatible MP4 media file was found in the VAST response.", "high", 3),
        (516, "TRACKING_PIXEL_TIMEOUT", "Tracking pixel request timed out before confirming playback.", "medium", 4),
    ]
    error_id = 601
    for creative_id_ref, code, message, severity, count in error_specs:
        for index in range(count):
            errors.append(
                VastValidationError(
                    id=error_id,
                    creative_id=creative_id_ref,
                    error_code=code,
                    error_message=message,
                    severity=severity,
                    detected_at=datetime.combine(TODAY - timedelta(hours=index * 4 // 24), time(hour=(8 + index) % 24)),
                )
            )
            error_id += 1

    pacing_snapshots: list[PacingSnapshot] = []
    pacing_profiles = {
        1045: [72, 70, 68, 64, 61, 58],
        1046: [55, 50, 48, 45, 43, 41],
        1047: [92, 94, 96, 95, 97, 99],
        1048: [66, 60, 55, 47, 43, 39],
        1049: [105, 108, 110, 112, 116, 118],
        1050: [70, 66, 61, 57, 53, 49],
        1051: [58, 50, 44, 38, 34, 29],
    }
    snapshot_id = 701
    for campaign in campaigns:
        for offset, pct in enumerate(pacing_profiles[campaign.id]):
            snapshot_date = TODAY - timedelta(days=5 - offset)
            expected = round(campaign.goal_impressions * ((snapshot_date - campaign.start_date).days + 1) / max((campaign.end_date - campaign.start_date).days + 1, 1))
            actual = round(expected * pct / 100)
            pacing_snapshots.append(
                PacingSnapshot(
                    id=snapshot_id,
                    campaign_id=campaign.id,
                    snapshot_date=snapshot_date,
                    expected_delivery=max(expected, 0),
                    actual_delivery=max(actual, 0),
                    pacing_percentage=float(pct),
                    risk_level=risk_for_pacing(float(pct)),
                )
            )
            snapshot_id += 1

    ad_requests: list[AdRequest] = []
    bid_responses: list[BidResponse] = []
    impressions: list[Impression] = []
    request_id = 801
    bid_id = 1801
    impression_id = 2601

    campaign_weights = [1045, 1045, 1045, 1046, 1046, 1047, 1047, 1048, 1048, 1049]
    segment_by_id = {segment.id: segment for segment in inventory_segments}
    for index in range(1000):
        campaign_id = random.choice(campaign_weights)
        campaign = next(item for item in campaigns if item.id == campaign_id)
        if campaign_id == 1045:
            segment_id = random.choice([401, 402, 404, 410])
        elif campaign_id == 1046:
            segment_id = random.choice([404, 405, 402])
        elif campaign_id == 1047:
            segment_id = random.choice([405, 407, 409])
        elif campaign_id == 1048:
            segment_id = random.choice([406, 407, 408])
        else:
            segment_id = random.choice([401, 402, 403])
        segment = segment_by_id[segment_id]

        failure_reason = None
        status = "eligible"
        if campaign_id == 1045 and (segment.country == "AT" or segment.content_category != "Sports" or segment.device_type != "CTV"):
            status = "failed"
            failure_reason = "targeting_mismatch"
        elif campaign_id == 1046 and random.random() < 0.46:
            status = "failed"
            failure_reason = "frequency_cap_exceeded"
        elif campaign_id == 1048 and segment.device_type != "CTV":
            status = "failed"
            failure_reason = "device_targeting_mismatch"
        elif campaign_id == 1048 and segment.content_category == "Gaming":
            status = "failed"
            failure_reason = "publisher_category_block"
        elif campaign_id != 1049 and random.random() < 0.08:
            status = "failed"
            failure_reason = "shared_inventory_consumed_by_high_priority_campaign"

        window_start = max(campaign.start_date, TODAY - timedelta(days=8))
        if campaign_id == 1048:
            window_start = max(window_start, campaign.start_date + timedelta(days=3))
        day_span = max((TODAY - window_start).days, 0)
        timestamp = datetime.combine(window_start + timedelta(days=random.randint(0, day_span)), time(hour=random.randint(0, 23), minute=random.randint(0, 59)))
        ad_request = AdRequest(
            id=request_id,
            campaign_id=campaign_id,
            publisher_id=segment.publisher_id,
            inventory_segment_id=segment.id,
            timestamp=timestamp,
            device_type=segment.device_type,
            country=segment.country,
            content_category=segment.content_category,
            request_status=status,
            failure_reason=failure_reason,
        )
        ad_requests.append(ad_request)

        if index < 300:
            floor = float(segment.floor_price)
            if campaign_id == 1047:
                bid_price = round(random.uniform(7.0, 11.2), 2)
            elif campaign_id == 1045:
                bid_price = round(random.uniform(17.2, 21.0), 2)
            elif campaign_id == 1048:
                bid_price = round(random.uniform(11.0, 16.0), 2)
            else:
                bid_price = round(random.uniform(floor - 2.5, floor + 4.0), 2)
            won = status == "eligible" and bid_price >= floor and random.random() > 0.18
            loss_reason = None if won else ("bid_below_floor" if bid_price < floor else failure_reason or "auction_lost")
            bid_responses.append(
                BidResponse(
                    id=bid_id,
                    campaign_id=campaign_id,
                    ad_request_id=request_id,
                    bid_price=bid_price,
                    floor_price=floor,
                    won=won,
                    loss_reason=loss_reason,
                )
            )
            bid_id += 1

        request_id += 1

    eligible_requests = [request for request in ad_requests if request.request_status == "eligible"]
    for request in eligible_requests[:500]:
        impressions.append(
            Impression(
                id=impression_id,
                campaign_id=request.campaign_id,
                publisher_id=request.publisher_id,
                timestamp=request.timestamp + timedelta(seconds=random.randint(1, 45)),
                device_type=request.device_type,
                country=request.country,
                content_category=request.content_category,
                revenue=round(random.uniform(0.018, 0.055), 4),
            )
        )
        impression_id += 1

    # Isolated RNG instance: extending the campaign roster below must never perturb
    # the shared `random` module sequence consumed above, since golden evaluation
    # cases and backend tests are tuned to the exact 1045-1049 evidence it produces.
    new_campaign_rng = random.Random(2050)
    new_campaign_specs = {
        1050: {
            "segments": [411, 412],
            "failure_reason": "publisher_allocation_below_forecast",
            "failure_rate": 0.50,
            "bid_range": (17.5, 21.0),
        },
        1051: {
            "segments": [413, 413, 413, 414],
            "failure_reason": "weekend_inventory_concentration",
            "failure_rate": 0.48,
            "bid_range": (13.5, 17.5),
        },
    }
    for new_campaign_id, spec in new_campaign_specs.items():
        new_campaign = next(item for item in campaigns if item.id == new_campaign_id)
        window_start = max(new_campaign.start_date, TODAY - timedelta(days=8))
        if new_campaign_id == 1051:
            window_start = max(window_start, new_campaign.start_date + timedelta(days=4))
        day_span = max((TODAY - window_start).days, 0)
        for _ in range(220):
            segment_id = new_campaign_rng.choice(spec["segments"])
            segment = segment_by_id[segment_id]
            status = "eligible"
            failure_reason = None
            if new_campaign_rng.random() < spec["failure_rate"]:
                status = "failed"
                failure_reason = spec["failure_reason"]
            timestamp = datetime.combine(
                window_start + timedelta(days=new_campaign_rng.randint(0, day_span)),
                time(hour=new_campaign_rng.randint(0, 23), minute=new_campaign_rng.randint(0, 59)),
            )
            ad_request = AdRequest(
                id=request_id,
                campaign_id=new_campaign_id,
                publisher_id=segment.publisher_id,
                inventory_segment_id=segment.id,
                timestamp=timestamp,
                device_type=segment.device_type,
                country=segment.country,
                content_category=segment.content_category,
                request_status=status,
                failure_reason=failure_reason,
            )
            ad_requests.append(ad_request)

            floor = float(segment.floor_price)
            bid_price = round(new_campaign_rng.uniform(*spec["bid_range"]), 2)
            won = status == "eligible" and bid_price >= floor and new_campaign_rng.random() > 0.18
            loss_reason = None if won else ("bid_below_floor" if bid_price < floor else failure_reason or "auction_lost")
            bid_responses.append(
                BidResponse(
                    id=bid_id,
                    campaign_id=new_campaign_id,
                    ad_request_id=request_id,
                    bid_price=bid_price,
                    floor_price=floor,
                    won=won,
                    loss_reason=loss_reason,
                )
            )
            bid_id += 1
            request_id += 1

    new_eligible_requests = [
        request
        for request in ad_requests
        if request.campaign_id in new_campaign_specs and request.request_status == "eligible"
    ]
    for request in new_eligible_requests:
        impressions.append(
            Impression(
                id=impression_id,
                campaign_id=request.campaign_id,
                publisher_id=request.publisher_id,
                timestamp=request.timestamp + timedelta(seconds=new_campaign_rng.randint(1, 45)),
                device_type=request.device_type,
                country=request.country,
                content_category=request.content_category,
                revenue=round(new_campaign_rng.uniform(0.018, 0.055), 4),
            )
        )
        impression_id += 1

    recommendations = [
        Recommendation(
            campaign_id=1045,
            title="Expand eligible CTV inventory",
            description="Relax the overly narrow device and geo constraints on a controlled test basis while preserving core brand-safety tiers, or add DE entertainment CTV supply.",
            expected_impact="High",
            risk_level="Medium",
            status="pending",
            created_at=utc_now(),
        ),
        Recommendation(
            campaign_id=1046,
            title="Replace rejected creative",
            description="Request a corrected companion asset from the creative agency and resubmit the addressable creative for revalidation.",
            expected_impact="High",
            risk_level="Low",
            status="approved",
            created_at=utc_now() - timedelta(days=3),
            decision_reason="Corrected VAST tag received from the creative agency and revalidated; approved to resume full delivery on the addressable flight.",
            decided_at=utc_now() - timedelta(days=3),
            decided_by_user_id=4,
        ),
        Recommendation(
            campaign_id=1047,
            title="Reallocate budget from underperforming segment",
            description="Shift spend away from the low-performing desktop finance and lifestyle video segment toward proven retail-audience CTV supply instead of raising bids further.",
            expected_impact="High",
            risk_level="Medium",
            status="rejected",
            created_at=utc_now() - timedelta(days=5),
            decision_reason="Budget increase deferred pending Q3 reforecast; monitor segment efficiency before committing incremental spend on underperforming inventory.",
            decided_at=utc_now() - timedelta(days=4),
            decided_by_user_id=4,
        ),
        Recommendation(
            campaign_id=1048,
            title="Expand eligible CTV inventory",
            description="Relax the combined SE/NO geo, CTV-only device, and frequency-cap constraints, or add Nordic CTV entertainment supply, to close the delivery gap before client escalation.",
            expected_impact="High",
            risk_level="Low",
            status="pending",
            created_at=utc_now(),
        ),
        Recommendation(
            campaign_id=1049,
            title="Confirm sponsorship priority allocation",
            description="Confirm the flagship sponsorship's high-priority allocation is intentional and reserve protected shared inventory for standard-priority peer campaigns for the remainder of the flight.",
            expected_impact="Medium",
            risk_level="Low",
            status="approved",
            created_at=utc_now() - timedelta(days=2),
            decision_reason="Sponsorship priority is intentional for the 5G launch flight. Reserved a protected allocation for peer campaigns to reduce shared-inventory pressure for the remainder of the window.",
            decided_at=utc_now() - timedelta(days=2),
            decided_by_user_id=1,
        ),
        Recommendation(
            campaign_id=1050,
            title="Shift budget to available premium CTV supply",
            description="Shift budget from the constrained programmatic finance segment, where publisher inventory allocation is running below forecast, to available premium CTV supply with comparable brand suitability.",
            expected_impact="High",
            risk_level="Medium",
            status="pending",
            created_at=utc_now(),
        ),
        Recommendation(
            campaign_id=1051,
            title="Expedite creative approval and rebalance flight",
            description="Expedite the pending creative sign-off and rebalance the flight toward available weekend inventory while working with publisher operations to add weekday supply for the remaining window.",
            expected_impact="High",
            risk_level="Medium",
            status="pending",
            created_at=utc_now(),
        ),
    ]

    return {
        "users": users,
        "advertisers": advertisers,
        "publishers": publishers,
        "campaigns": campaigns,
        "inventory_segments": inventory_segments,
        "creatives": creatives,
        "vast_validation_errors": errors,
        "ad_requests": ad_requests,
        "impressions": impressions,
        "bid_responses": bid_responses,
        "pacing_snapshots": pacing_snapshots,
        "recommendations": recommendations,
    }


SEEDED_MODELS = [
    KnowledgeChunk,
    AgentAuditLog,
    BidResponse,
    Impression,
    AdRequest,
    VastValidationError,
    Creative,
    PacingSnapshot,
    Recommendation,
    Campaign,
    InventorySegment,
    Publisher,
    Advertiser,
    User,
]


def clear_existing_data(db) -> None:
    if engine.dialect.name == "postgresql":
        table_names = ", ".join(model.__tablename__ for model in SEEDED_MODELS)
        db.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
        return

    for model in SEEDED_MODELS:
        db.execute(delete(model))


def sync_postgres_sequences(db) -> None:
    if engine.dialect.name != "postgresql":
        return

    for model in SEEDED_MODELS:
        table_name = model.__tablename__
        db.execute(
            text(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('{table_name}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table_name}), 1),
                    (SELECT COUNT(*) FROM {table_name}) > 0
                )
                """
            )
        )


def seed_database() -> None:
    create_all()
    data = build_seed_data()
    with SessionLocal() as db:
        clear_existing_data(db)
        db.commit()

        for key in [
            "users",
            "advertisers",
            "publishers",
            "inventory_segments",
            "campaigns",
            "creatives",
            "vast_validation_errors",
            "ad_requests",
            "impressions",
            "bid_responses",
            "pacing_snapshots",
            "recommendations",
        ]:
            db.add_all(data[key])
            db.flush()
        sync_postgres_sequences(db)
        db.commit()

    for filename, key in [
        ("advertisers.csv", "advertisers"),
        ("publishers.csv", "publishers"),
        ("campaigns.csv", "campaigns"),
        ("inventory_segments.csv", "inventory_segments"),
        ("creatives.csv", "creatives"),
        ("vast_validation_errors.csv", "vast_validation_errors"),
        ("ad_requests.csv", "ad_requests"),
        ("impressions.csv", "impressions"),
        ("bid_responses.csv", "bid_responses"),
        ("pacing_snapshots.csv", "pacing_snapshots"),
    ]:
        write_csv(filename, data[key])

    print(
        json.dumps(
            {
                "campaigns": len(data["campaigns"]),
                "creatives": len(data["creatives"]),
                "ad_requests": len(data["ad_requests"]),
                "impressions": len(data["impressions"]),
                "bid_responses": len(data["bid_responses"]),
                "vast_validation_errors": len(data["vast_validation_errors"]),
                "pacing_snapshots": len(data["pacing_snapshots"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    seed_database()
