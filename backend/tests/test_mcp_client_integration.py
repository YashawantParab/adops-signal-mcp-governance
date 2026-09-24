"""Direct integration test proving the backend's MCP client speaks the real MCP
protocol to the actual standalone mcp-server (mcp-server/adops_signal_mcp),
over a real stdio subprocess - not a mock and not a direct Python function call.
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.mcp_client import DEFAULT_MCP_SERVER_DIR, MCPAgentClient, MCPClientError
from app.database import Base
from seed import build_seed_data

pytestmark = pytest.mark.skipif(
    not DEFAULT_MCP_SERVER_DIR.exists(), reason="mcp-server/ is not present in this checkout"
)

EXPECTED_TOOL_NAMES = {
    "ping_adops_signal",
    "get_campaign_health",
    "get_campaign_pacing",
    "get_vast_validation_summary",
    "get_brand_safety_findings",
    "get_recommendation_history",
    "search_policy_context",
}


def _seed_sqlite_db(tmp_path) -> str:
    db_path = tmp_path / "mcp_client_integration.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
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
        db.flush()
    db.commit()
    db.close()
    engine.dispose()
    return f"sqlite:///{db_path}"


def test_mcp_client_lists_real_tools_from_the_actual_server(tmp_path):
    database_url = _seed_sqlite_db(tmp_path)

    async def run() -> list[str]:
        async with MCPAgentClient(extra_env={"DATABASE_URL": database_url}) as client:
            tools = await client.list_tools()
        return [tool.name for tool in tools]

    tool_names = asyncio.run(run())
    assert EXPECTED_TOOL_NAMES.issubset(set(tool_names))


def test_mcp_client_calls_real_tool_and_receives_real_server_data(tmp_path):
    database_url = _seed_sqlite_db(tmp_path)

    async def run():
        async with MCPAgentClient(extra_env={"DATABASE_URL": database_url}) as client:
            ping = await client.call_tool("ping_adops_signal", {})
            health = await client.call_tool("get_campaign_health", {"campaign_id": 1045})
        return ping, health

    ping, health = asyncio.run(run())

    assert ping.ok is True
    assert ping.data.get("ok") is True

    assert health.ok is True
    assert health.data["ok"] is True
    assert health.data["campaign_id"] == 1045
    assert "risk_level" in health.data["health"]


def test_mcp_client_reports_server_error_for_unknown_campaign(tmp_path):
    database_url = _seed_sqlite_db(tmp_path)

    async def run():
        async with MCPAgentClient(extra_env={"DATABASE_URL": database_url}) as client:
            return await client.call_tool("get_campaign_health", {"campaign_id": 999999})

    result = asyncio.run(run())
    assert result.data.get("ok") is False
    assert result.data.get("error", {}).get("code") == "CAMPAIGN_NOT_FOUND"


def test_mcp_client_raises_typed_error_when_server_command_is_invalid(tmp_path):
    from app.config import Settings

    async def run():
        settings = Settings(mcp_server_command="definitely-not-a-real-executable")
        async with MCPAgentClient(settings=settings):
            pass  # pragma: no cover - should never get here

    with pytest.raises(MCPClientError):
        asyncio.run(run())
