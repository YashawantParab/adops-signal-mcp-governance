from __future__ import annotations

from adops_signal_mcp.tools import (
    get_brand_safety_findings,
    get_campaign_health,
    get_campaign_pacing,
    get_recommendation_history,
    get_vast_validation_summary,
    ping_adops_signal,
    search_policy_context,
)


def test_ping_adops_signal_reports_database_ready() -> None:
    result = ping_adops_signal()

    assert result["ok"] is True
    assert result["service"] == "SignalOps AI"
    assert result["database"]["connected"] is True


def test_get_campaign_health_uses_seeded_campaign_data() -> None:
    result = get_campaign_health(1045)

    assert result["ok"] is True
    assert result["campaign_id"] == 1045
    assert result["campaign"]["campaign_name"] == "RheinAuto CTV Launch"
    assert result["health"]["campaign_id"] == 1045
    assert "pacing_percentage" in result["health"]
    assert result["metadata"]["service_function"] == "app.services.campaign_service.get_campaign_health"


def test_get_campaign_health_rejects_invalid_campaign_id() -> None:
    result = get_campaign_health(0)

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_CAMPAIGN_ID"


def test_get_campaign_health_reports_missing_campaign() -> None:
    result = get_campaign_health(999999)

    assert result["ok"] is False
    assert result["error"]["code"] == "CAMPAIGN_NOT_FOUND"


def test_get_campaign_pacing_returns_latest_and_history() -> None:
    result = get_campaign_pacing(1045)

    assert result["ok"] is True
    assert result["campaign_id"] == 1045
    assert result["latest"]["pacing_percentage"] == 58.0
    assert result["trend"]["direction"] == "declining"
    assert len(result["history"]) >= 2


def test_get_vast_validation_summary_uses_persisted_errors() -> None:
    result = get_vast_validation_summary(1046)

    assert result["ok"] is True
    assert result["campaign_id"] == 1046
    assert result["valid"] is False
    assert result["rejected_count"] == 1
    assert result["error_code_counts"]["COMPANION_MISSING"] == 4


def test_get_brand_safety_findings_returns_governance_findings() -> None:
    result = get_brand_safety_findings(1045)

    assert result["ok"] is True
    assert result["campaign_id"] == 1045
    assert result["read_only"] is True
    assert any(item["type"] == "recommendation_policy_reference" for item in result["findings"])


def test_get_recommendation_history_returns_decision_metadata() -> None:
    result = get_recommendation_history(1046)

    assert result["ok"] is True
    assert result["campaign_id"] == 1046
    assert result["status_counts"]["approved"] == 1
    assert result["recommendations"][0]["decided_by_name"] == "Daniel Keller"


def test_search_policy_context_returns_keyword_matches() -> None:
    result = search_policy_context("budget shift human approval")

    assert result["ok"] is True
    assert result["retrieval"]["method"] == "keyword"
    assert result["retrieval"]["vector_db_used"] is False
    assert any(match["source"] == "docs/policies/budget-shift-policy.md" for match in result["matches"])


def test_search_policy_context_rejects_empty_query() -> None:
    result = search_policy_context("   ")

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_POLICY_QUERY"
