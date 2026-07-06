from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent import AdOpsSignalAgent
from app.database import Base
from app.models import AgentAuditLog, Campaign, Recommendation
from app.services.recommendation_service import update_recommendation_status
from seed import build_seed_data

CASES_PATH = Path(__file__).with_name("golden_cases.json")

# Client-safe briefs must never leak these internal-only terms. This is a hallucination/
# leakage guardrail, not a diagnosis-quality check: it fails if raw auction, publisher, or
# execution internals surface in advertiser-facing language.
FORBIDDEN_CLIENT_SAFE_TERMS = [
    "publisher floor",
    "floor price",
    "loss reason",
    "already fixed",
    "already applied",
    "vast_validation",
    "sql_analysis_tool",
]


def build_session():
    temp_dir = tempfile.TemporaryDirectory()
    engine = create_engine(f"sqlite:///{Path(temp_dir.name) / 'evaluation.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
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
        session.add_all(data[key])
        session.flush()
    session.commit()
    return temp_dir, session


def _check_client_safe_guardrails(db, agent: AdOpsSignalAgent, campaign_ids: list[int]) -> list[dict]:
    """Generate client-safe briefs and check they never leak internal-only details."""
    checks = []
    for campaign_id in campaign_ids:
        campaign = db.get(Campaign, campaign_id)
        summary = agent.client_safe_summary(db, campaign, None)
        lowered = summary.lower()
        violations = [term for term in FORBIDDEN_CLIENT_SAFE_TERMS if term in lowered]
        checks.append(
            {
                "campaign_id": campaign_id,
                "mentions_campaign_name": campaign.campaign_name in summary,
                "violations": violations,
                "passed": not violations and campaign.campaign_name in summary,
            }
        )
    return checks


def _check_governance_workflow(db, agent: AdOpsSignalAgent) -> dict:
    """Diagnose -> approve -> audit round trip, the same path the UI drives."""
    campaign = db.get(Campaign, 1048)
    diagnosis = agent.diagnose(
        db, campaign, "Why is this campaign underdelivering?", user_id=1, request_id="eval-governance-check"
    )
    pending = next((item for item in diagnosis.recommendations if item.status == "pending"), None)
    if not pending:
        return {"passed": False, "reason": "diagnosis produced no pending recommendation to govern"}

    decided = update_recommendation_status(
        db,
        pending.id,
        "approved",
        user_id=1,
        reason="Evaluation harness governance round trip.",
    )
    audit = db.execute(
        select(AgentAuditLog)
        .where(AgentAuditLog.campaign_id == campaign.id)
        .order_by(AgentAuditLog.id.desc())
    ).scalars().first()

    passed = bool(
        decided
        and decided.status == "approved"
        and decided.decided_by_user_id == 1
        and decided.decision_reason
        and audit
        and audit.request_id == "eval-governance-check"
    )
    return {
        "passed": passed,
        "recommendation_id": pending.id,
        "audit_log_id": audit.id if audit else None,
    }


def evaluate() -> dict:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    temp_dir, db = build_session()
    agent = AdOpsSignalAgent()
    results = []
    try:
        for case in cases:
            campaign = db.get(Campaign, case["campaign_id"])
            response = agent.diagnose(db, campaign, case["query"])
            actual = {cause.cause.lower() for cause in response.root_causes}
            expected = {cause.lower() for cause in case["expected_all"]}
            cause_hits = sum(1 for cause in expected if cause in actual)
            evidence_text = " ".join(item.message.lower() for item in response.evidence)
            evidence_terms = case.get("required_evidence_terms", [])
            evidence_hits = sum(1 for term in evidence_terms if term.lower() in evidence_text)
            # Root-cause recall and evidence grounding are the release-gating checks (unchanged
            # from prior versions of this suite). Playbook relevance is reported separately and
            # does NOT gate "passed": the local hash-embedding fallback used without an OpenAI
            # key is a noisy retrieval signal for short queries by design (see EVALUATION_REPORT.md),
            # so gating on it would produce false failures rather than a meaningful quality signal.
            expected_source = case.get("expected_playbook_source")
            playbook_relevant = (
                expected_source in response.retrieved_documents if expected_source else None
            )
            passed = cause_hits == len(expected) and evidence_hits == len(evidence_terms)
            results.append(
                {
                    "id": case["id"],
                    "passed": passed,
                    "execution_mode": response.execution_mode,
                    "expected": sorted(expected),
                    "actual": sorted(actual),
                    "evidence_grounded": all(cause.evidence_ids for cause in response.root_causes),
                    "playbook_relevant": playbook_relevant,
                }
            )

        client_safe_checks = _check_client_safe_guardrails(db, agent, campaign_ids=[1046, 1048])
        governance_check = _check_governance_workflow(db, agent)
    finally:
        db.close()
        temp_dir.cleanup()

    passed = sum(1 for result in results if result["passed"])
    grounded = sum(1 for result in results if result["evidence_grounded"])
    playbook_checks = [result for result in results if result["playbook_relevant"] is not None]
    playbook_relevance_rate = (
        round(sum(1 for result in playbook_checks if result["playbook_relevant"]) / len(playbook_checks), 4)
        if playbook_checks
        else None
    )
    client_safe_guardrail_pass_rate = round(
        sum(1 for check in client_safe_checks if check["passed"]) / len(client_safe_checks), 4
    )
    return {
        "cases": len(results),
        "passed": passed,
        "root_cause_recall": round(passed / len(results), 4),
        "evidence_grounding_rate": round(grounded / len(results), 4),
        "playbook_relevance_rate": playbook_relevance_rate,
        "client_safe_guardrail_pass_rate": client_safe_guardrail_pass_rate,
        "governance_workflow_passed": governance_check["passed"],
        "llm_configured": bool(os.getenv("OPENAI_API_KEY")),
        "results": results,
        "client_safe_checks": client_safe_checks,
        "governance_check": governance_check,
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
