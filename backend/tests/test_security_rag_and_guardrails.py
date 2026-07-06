import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent import AdOpsSignalAgent
from app.config import get_settings
from app.database import Base
from app.models import Campaign, Recommendation, User
from app.security import create_access_token, hash_password, verify_password
from app.services.rag_service import index_knowledge_base, retrieve
from app.services.recommendation_service import update_recommendation_status
from app.services.vast_service import validate_vast
from seed import build_seed_data


def session_with_seed(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'quality.db'}")
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
    return db


def test_passwords_use_salted_pbkdf2_and_verify():
    first = hash_password("correct-horse-battery-staple")
    second = hash_password("correct-horse-battery-staple")
    assert first != second
    assert verify_password("correct-horse-battery-staple", first)
    assert not verify_password("wrong-password", first)


def test_access_token_contains_role_and_audience():
    settings = get_settings()
    user = User(id=42, email="operator@example.test", full_name="Operator", password_hash="x", role="adops_manager")
    token, expires_in = create_access_token(user)
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        audience="adops-signal-web",
        issuer="adops-signal",
    )
    assert payload["sub"] == "42"
    assert payload["role"] == "adops_manager"
    assert expires_in > 0


def test_vector_rag_indexes_and_retrieves_operational_guidance(tmp_path):
    db = session_with_seed(tmp_path)
    assert index_knowledge_base(db, force=True) >= 4
    matches = retrieve(db, "VAST timeout wrapper latency creative", limit=3)
    assert matches
    assert any("vast" in item.source.lower() or "vast" in item.content.lower() for item in matches)
    assert all(-1 <= item.score <= 1 for item in matches)


def test_every_agent_claim_has_evidence_provenance(tmp_path):
    db = session_with_seed(tmp_path)
    campaign = db.get(Campaign, 1048)
    result = AdOpsSignalAgent().diagnose(db, campaign, "Why did delivery collapse?")
    known_ids = {item.id for item in result.evidence}
    assert result.root_causes
    assert all(cause.evidence_ids for cause in result.root_causes)
    assert all(set(cause.evidence_ids).issubset(known_ids) for cause in result.root_causes)


def test_fallback_causes_cite_semantically_matching_evidence(tmp_path):
    db = session_with_seed(tmp_path)
    campaign = db.get(Campaign, 1048)
    result = AdOpsSignalAgent().diagnose(db, campaign, "Why did delivery collapse?")
    evidence_by_id = {item.id: item for item in result.evidence}

    vast_cause = next(cause for cause in result.root_causes if cause.cause == "VAST validation issue")
    bid_cause = next(cause for cause in result.root_causes if cause.cause == "Bid price below floor")

    assert all("vast_validation_errors" in evidence_by_id[evidence_id].source for evidence_id in vast_cause.evidence_ids)
    assert all("bid_responses" in evidence_by_id[evidence_id].source for evidence_id in bid_cause.evidence_ids)


def test_vast_url_timeout_is_blocked(tmp_path):
    db = session_with_seed(tmp_path)
    result = validate_vast(db, None, "https://ads.example.test/slow-timeout.xml")
    assert not result.valid
    assert result.approval_status == "needs_review"
    assert result.errors[0].error_code == "VAST_TIMEOUT"


def test_recommendation_decision_records_human_provenance(tmp_path):
    db = session_with_seed(tmp_path)
    recommendation = db.query(Recommendation).filter_by(status="pending").first()
    updated = update_recommendation_status(
        db,
        recommendation.id,
        "approved",
        user_id=1,
        reason="Validated against current inventory forecast.",
    )
    assert updated.status == "approved"
    assert updated.decided_by_user_id == 1
    assert updated.decided_at is not None
    assert updated.decision_reason == "Validated against current inventory forecast."
