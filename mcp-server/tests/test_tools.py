from __future__ import annotations

from adops_signal_mcp.tools import get_campaign_health, ping_adops_signal


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

