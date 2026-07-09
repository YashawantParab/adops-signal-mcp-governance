import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.agent import AdOpsSignalAgent
from app.database import Base
from app.models import AgentAuditLog, Campaign, Recommendation
from app.security import (
    DEMO_VIEWER_ROLE,
    build_demo_viewer,
    create_demo_access_token,
    get_current_user,
    require_roles,
)
from seed import build_seed_data


def session_with_seed(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'demo.db'}")
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


def test_demo_session_token_resolves_to_read_only_role(tmp_path):
    db = session_with_seed(tmp_path)
    token, expires_in = create_demo_access_token()
    assert expires_in > 0
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    user = get_current_user(credentials=credentials, db=db)
    assert user.role == DEMO_VIEWER_ROLE
    assert user.is_active


def test_demo_viewer_role_is_rejected_by_approval_endpoint():
    demo_user = build_demo_viewer()
    dependency = require_roles("admin", "adops_manager")
    with pytest.raises(HTTPException) as excinfo:
        dependency(user=demo_user)
    assert excinfo.value.status_code == 403


def test_diagnose_with_persist_false_writes_no_audit_or_recommendation_rows(tmp_path):
    db = session_with_seed(tmp_path)
    campaign = db.get(Campaign, 1048)
    recommendations_before = list(db.execute(select(Recommendation).where(Recommendation.campaign_id == 1048)).scalars())
    snapshot_before = {item.id: (item.description, item.status) for item in recommendations_before}

    result = AdOpsSignalAgent().diagnose(
        db,
        campaign,
        "Why is this campaign underdelivering?",
        user_id=build_demo_viewer().id,
        persist=False,
    )

    assert result.root_causes
    assert result.recommendations

    audit_rows = list(db.execute(select(AgentAuditLog).where(AgentAuditLog.campaign_id == 1048)).scalars())
    assert audit_rows == []

    recommendations_after = list(db.execute(select(Recommendation).where(Recommendation.campaign_id == 1048)).scalars())
    snapshot_after = {item.id: (item.description, item.status) for item in recommendations_after}
    assert snapshot_after == snapshot_before
    assert len(recommendations_after) == len(recommendations_before)
