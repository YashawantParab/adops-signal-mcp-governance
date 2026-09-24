from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.agent.mcp_client import MCPCallResult, MCPClientError
from app.database import Base
from app.models import AgentRun, Campaign, MCPToolCall
from app.services.governance_wrapper import GovernanceDenied, governed_tool_call, validate_tool_call
from seed import build_seed_data


def seeded_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'governance.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    data = build_seed_data()
    for key in ["advertisers", "publishers", "inventory_segments", "campaigns"]:
        db.add_all(data[key])
        db.flush()
    db.commit()

    run = AgentRun(
        user_query="test",
        campaign_id=1045,
        status="running",
        risk_level="LOW",
        risk_score=0.0,
        final_recommendation="",
        approval_required=False,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return db, run


class FakeMCPClient:
    """Stubs the real MCP client's call_tool for fast, deterministic wrapper tests.
    The real stdio round trip is proven separately in test_mcp_client_integration.py."""

    def __init__(self, *, result: MCPCallResult | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, arguments: dict) -> MCPCallResult:
        self.calls.append((name, arguments))
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


# --- validate_tool_call (pure, synchronous) ----------------------------------


def test_unknown_tool_is_denied():
    with pytest.raises(GovernanceDenied) as excinfo:
        validate_tool_call("delete_campaign", {}, scoped_campaign_id=1045)
    assert excinfo.value.reason_code == "UNKNOWN_TOOL"


def test_out_of_scope_campaign_is_denied():
    with pytest.raises(GovernanceDenied) as excinfo:
        validate_tool_call("get_campaign_health", {"campaign_id": 1046}, scoped_campaign_id=1045)
    assert excinfo.value.reason_code == "OUT_OF_SCOPE"


def test_permission_denied_for_non_read_tool(monkeypatch):
    import app.services.governance_wrapper as wrapper

    class FakeDescriptor:
        name = "get_campaign_health"
        permission_level = "write"

    monkeypatch.setitem(wrapper._TOOL_DESCRIPTOR_BY_NAME, "get_campaign_health", FakeDescriptor())
    with pytest.raises(GovernanceDenied) as excinfo:
        validate_tool_call("get_campaign_health", {"campaign_id": 1045}, scoped_campaign_id=1045)
    assert excinfo.value.reason_code == "PERMISSION_DENIED"


def test_in_scope_read_only_tool_is_allowed():
    validate_tool_call("get_campaign_health", {"campaign_id": 1045}, scoped_campaign_id=1045)  # no raise


# --- governed_tool_call (async, writes MCPToolCall audit rows) --------------


def test_governed_tool_call_logs_success(tmp_path):
    db, run = seeded_session(tmp_path)
    client = FakeMCPClient(result=MCPCallResult(ok=True, data={"ok": True, "risk_level": "High"}, is_error=False))

    outcome = asyncio.run(
        governed_tool_call(
            db,
            agent_run_id=run.id,
            mcp_client=client,
            tool_name="get_campaign_health",
            arguments={"campaign_id": 1045},
            scoped_campaign_id=1045,
        )
    )

    assert outcome.ok is True
    assert client.calls == [("get_campaign_health", {"campaign_id": 1045})]

    row = db.execute(select(MCPToolCall).where(MCPToolCall.id == outcome.tool_call_id)).scalar_one()
    assert row.status == "success"
    assert row.output_json["risk_level"] == "High"
    assert row.latency_ms >= 1


def test_governed_tool_call_logs_denied_without_calling_mcp(tmp_path):
    db, run = seeded_session(tmp_path)
    client = FakeMCPClient(result=MCPCallResult(ok=True, data={"ok": True}, is_error=False))

    outcome = asyncio.run(
        governed_tool_call(
            db,
            agent_run_id=run.id,
            mcp_client=client,
            tool_name="not_a_real_tool",
            arguments={},
            scoped_campaign_id=1045,
        )
    )

    assert outcome.ok is False
    assert outcome.error_category == "UNKNOWN_TOOL"
    assert client.calls == []  # MCP was never reached

    row = db.execute(select(MCPToolCall).where(MCPToolCall.id == outcome.tool_call_id)).scalar_one()
    assert row.status == "denied"
    assert row.output_json["error"]["code"] == "UNKNOWN_TOOL"


def test_governed_tool_call_logs_mcp_failure(tmp_path):
    db, run = seeded_session(tmp_path)
    client = FakeMCPClient(error=MCPClientError("subprocess died"))

    outcome = asyncio.run(
        governed_tool_call(
            db,
            agent_run_id=run.id,
            mcp_client=client,
            tool_name="get_campaign_health",
            arguments={"campaign_id": 1045},
            scoped_campaign_id=1045,
        )
    )

    assert outcome.ok is False
    assert outcome.error_category == "MCP_CALL_FAILED"

    row = db.execute(select(MCPToolCall).where(MCPToolCall.id == outcome.tool_call_id)).scalar_one()
    assert row.status == "failed"
    assert "subprocess died" in row.output_json["error"]["message"]


def test_governed_tool_call_logs_tool_level_error(tmp_path):
    db, run = seeded_session(tmp_path)
    client = FakeMCPClient(
        result=MCPCallResult(
            ok=False,
            data={"ok": False, "error": {"code": "CAMPAIGN_NOT_FOUND", "message": "no such campaign"}},
            is_error=True,
        )
    )

    outcome = asyncio.run(
        governed_tool_call(
            db,
            agent_run_id=run.id,
            mcp_client=client,
            tool_name="get_campaign_health",
            arguments={"campaign_id": 1045},
            scoped_campaign_id=1045,
        )
    )

    assert outcome.ok is False
    assert outcome.error_category == "CAMPAIGN_NOT_FOUND"
    row = db.execute(select(MCPToolCall).where(MCPToolCall.id == outcome.tool_call_id)).scalar_one()
    assert row.status == "failed"
