from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent import AdOpsSignalAgent
from app.database import Base
from app.models import Campaign
from seed import build_seed_data

CASES_PATH = Path(__file__).with_name("golden_cases.json")


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


def evaluate() -> dict:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    temp_dir, db = build_session()
    results = []
    try:
        for case in cases:
            campaign = db.get(Campaign, case["campaign_id"])
            response = AdOpsSignalAgent().diagnose(db, campaign, case["query"])
            actual = {cause.cause.lower() for cause in response.root_causes}
            expected = {cause.lower() for cause in case["expected_all"]}
            cause_hits = sum(1 for cause in expected if cause in actual)
            evidence_text = " ".join(item.message.lower() for item in response.evidence)
            evidence_terms = case.get("required_evidence_terms", [])
            evidence_hits = sum(1 for term in evidence_terms if term.lower() in evidence_text)
            passed = cause_hits == len(expected) and evidence_hits == len(evidence_terms)
            results.append(
                {
                    "id": case["id"],
                    "passed": passed,
                    "execution_mode": response.execution_mode,
                    "expected": sorted(expected),
                    "actual": sorted(actual),
                    "evidence_grounded": all(cause.evidence_ids for cause in response.root_causes),
                }
            )
    finally:
        db.close()
        temp_dir.cleanup()

    passed = sum(1 for result in results if result["passed"])
    grounded = sum(1 for result in results if result["evidence_grounded"])
    return {
        "cases": len(results),
        "passed": passed,
        "root_cause_recall": round(passed / len(results), 4),
        "evidence_grounding_rate": round(grounded / len(results), 4),
        "llm_configured": bool(os.getenv("OPENAI_API_KEY")),
        "results": results,
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
