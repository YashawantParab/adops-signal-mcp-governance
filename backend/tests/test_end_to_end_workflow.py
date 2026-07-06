from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.agent import AdOpsSignalAgent
from app.database import Base
from app.models import AgentAuditLog, Campaign, Recommendation
from app.services.recommendation_service import update_recommendation_status
from seed import build_seed_data


def test_operator_workflow_from_diagnosis_to_governed_decision(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'workflow.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    data = build_seed_data()
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
    db.commit()

    campaign = db.get(Campaign, 1048)
    agent = AdOpsSignalAgent()
    diagnosis = agent.diagnose(
        db,
        campaign,
        "Why is this campaign underdelivering?",
        user_id=1,
        request_id="workflow-test",
    )

    assert diagnosis.root_causes
    assert diagnosis.evidence
    assert diagnosis.recommendations
    assert all(cause.evidence_ids for cause in diagnosis.root_causes)

    client_summary = agent.client_safe_summary(db, campaign, diagnosis.diagnosis, user_id=1)
    assert campaign.campaign_name in client_summary
    assert "publisher floor" not in client_summary.lower()

    recommendation = db.scalar(
        select(Recommendation)
        .where(Recommendation.campaign_id == campaign.id, Recommendation.status == "pending")
        .order_by(Recommendation.id.desc())
    )
    decided = update_recommendation_status(
        db,
        recommendation.id,
        "approved",
        user_id=1,
        reason="Evidence reviewed; proceed with a controlled recovery test.",
    )
    audit = db.scalar(
        select(AgentAuditLog)
        .where(AgentAuditLog.campaign_id == campaign.id)
        .order_by(AgentAuditLog.id.desc())
    )

    assert decided.status == "approved"
    assert decided.decided_by_user_id == 1
    assert decided.decision_reason
    assert audit.request_id == "workflow-test"
    assert audit.confidence_score == diagnosis.confidence_score

    repeated = agent.diagnose(
        db,
        campaign,
        "Why is this campaign underdelivering?",
        user_id=1,
        request_id="workflow-test-repeat",
    )
    repeated_match = next(item for item in repeated.recommendations if item.id == decided.id)
    assert repeated_match.status == "approved"
    assert repeated_match.decision_reason == decided.decision_reason
