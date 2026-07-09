from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent import AdOpsSignalAgent
from app.database import Base
from app.models import (
    AdRequest,
    Advertiser,
    BidResponse,
    Campaign,
    Creative,
    Impression,
    InventorySegment,
    PacingSnapshot,
    Publisher,
    Recommendation,
    VastValidationError,
)
from seed import build_seed_data


def seeded_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine)
    db = testing_session()
    data = build_seed_data()
    for key in [
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
    db.commit()
    return db, data


def test_seed_counts_are_deterministic(tmp_path):
    _, data = seeded_session(tmp_path)
    assert len(data["campaigns"]) == 7
    assert len(data["advertisers"]) == 7
    assert len(data["publishers"]) == 6
    assert len(data["inventory_segments"]) == 14
    assert len(data["creatives"]) == 28
    assert len(data["ad_requests"]) == 1440
    assert len(data["impressions"]) == 725
    assert len(data["bid_responses"]) == 740
    assert len(data["vast_validation_errors"]) == 20
    assert len(data["pacing_snapshots"]) == 42


def test_agent_detects_campaign_1045_delivery_blockers(tmp_path):
    db, _ = seeded_session(tmp_path)
    campaign = db.get(Campaign, 1045)
    result = AdOpsSignalAgent().diagnose(db, campaign, "Why is Campaign 1045 underdelivering?")
    causes = [cause.cause for cause in result.root_causes]
    assert "Narrow targeting" in causes
    assert "VAST validation issue" in causes
    assert result.confidence_score >= 0.8
    assert result.evidence


def test_agent_detects_rejected_creative_for_campaign_1046(tmp_path):
    db, _ = seeded_session(tmp_path)
    campaign = db.get(Campaign, 1046)
    result = AdOpsSignalAgent().diagnose(db, campaign, "Is creative causing delivery issues?")
    causes = [cause.cause for cause in result.root_causes]
    assert "Creative rejected" in causes
    assert any("rejected" in item.message.lower() for item in result.evidence)


def test_different_operator_questions_produce_different_investigations(tmp_path):
    db, _ = seeded_session(tmp_path)
    campaign = db.get(Campaign, 1045)
    agent = AdOpsSignalAgent()

    targeting = agent.diagnose(db, campaign, "Which targeting rule is killing delivery?")
    creative = agent.diagnose(db, campaign, "Is the VAST creative causing delivery issues?")
    feasibility = agent.diagnose(db, campaign, "Can this campaign still hit its goal by Friday?")

    assert targeting.query_intent == "targeting_inventory"
    assert creative.query_intent == "creative_vast"
    assert feasibility.query_intent == "goal_feasibility"
    assert targeting.diagnosis != creative.diagnosis != feasibility.diagnosis

    assert "targeting_analyzer_tool" in targeting.tools_called
    assert "vast_validation_tool" not in targeting.tools_called
    assert "vast_validation_tool" in creative.tools_called
    assert "targeting_analyzer_tool" not in creative.tools_called
    assert "goal_feasibility_tool" in feasibility.tools_called

    assert all(
        any(term in cause.cause.lower() for term in ("targeting", "inventory", "device", "shared"))
        for cause in targeting.root_causes
    )
    assert all(any(term in cause.cause.lower() for term in ("vast", "creative")) for cause in creative.root_causes)
    assert feasibility.root_causes[0].cause == "Goal attainment risk"
    assert "impressions per day" in feasibility.diagnosis
