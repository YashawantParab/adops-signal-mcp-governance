"""Tests for the hosted external MCP endpoint's auth/rate-limit/audit
middleware (app.hosted_mcp.ExternalMCPAuthMiddleware) in isolation, against a
minimal dummy downstream app - not the real FastMCP session manager.

The middleware genuinely wrapping the real FastMCP streamable-http session
manager (initialize -> notifications/initialized -> tools/call, real MCP
protocol, real tool results, real 429 after the rate limit is exhausted) was
verified manually against the actual mounted app in this session - see the
Phase 3 final report for the transcript. That path needs the full app's
startup/shutdown lifecycle (session manager lifespan) and a real database, so
it is not re-asserted here as a fast, hermetic unit test; this file instead
locks in the auth/rate-limit/audit contract the middleware itself owns.
"""
from __future__ import annotations

import pytest

import app.hosted_mcp as hosted_mcp
import app.rate_limit as rate_limit
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.database import Base
from app.models import ExternalMCPCall
from app.services.mcp_token_service import create_token


@pytest.fixture(autouse=True)
def _isolated_rate_limit_state():
    """check_rate_limit's bucket dict is module-level global state keyed by
    token id, and each test's fresh sqlite DB restarts token ids at 1 - without
    resetting this between tests, an earlier test's hits leak into the next
    one's budget."""
    rate_limit._hits.clear()
    yield
    rate_limit._hits.clear()


def build_test_app(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'hosted_mcp.db'}")
    Base.metadata.create_all(engine)
    # Must match app.database.SessionLocal's expire_on_commit=False - the real
    # middleware accesses token attributes after its `with SessionLocal()`
    # block closes (see app/hosted_mcp.py), which requires this setting.
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(hosted_mcp, "SessionLocal", session_factory)

    async def echo(request):
        return JSONResponse({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})

    app = Starlette(
        routes=[Route("/", echo, methods=["POST"])],
        middleware=[Middleware(hosted_mcp.ExternalMCPAuthMiddleware)],
    )
    return app, session_factory


def test_missing_token_is_rejected_and_audited(tmp_path, monkeypatch):
    app, session_factory = build_test_app(monkeypatch, tmp_path)
    with TestClient(app) as client:
        response = client.post("/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response.status_code == 401

    db = session_factory()
    row = db.execute(select(ExternalMCPCall)).scalar_one()
    assert row.token_id is None
    assert row.method == "unauthenticated"
    assert row.status_code == 401


def test_valid_token_passes_through_and_is_audited_with_tool_name(tmp_path, monkeypatch):
    app, session_factory = build_test_app(monkeypatch, tmp_path)
    db = session_factory()
    token, raw = create_token(db, name="Partner", rate_limit_per_minute=10)

    with TestClient(app) as client:
        response = client.post(
            "/",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_campaign_health", "arguments": {"campaign_id": 1045}}},
            headers={"Authorization": f"Bearer {raw}"},
        )
    assert response.status_code == 200

    row = db.execute(select(ExternalMCPCall).where(ExternalMCPCall.token_id == token.id)).scalar_one()
    assert row.method == "tools/call"
    assert row.tool_name == "get_campaign_health"
    assert row.status_code == 200


def test_rate_limit_exceeded_returns_429_and_stops_forwarding(tmp_path, monkeypatch):
    app, session_factory = build_test_app(monkeypatch, tmp_path)
    db = session_factory()
    token, raw = create_token(db, name="Bursty Partner", rate_limit_per_minute=2)
    headers = {"Authorization": f"Bearer {raw}"}

    with TestClient(app) as client:
        statuses = [client.post("/", json={"jsonrpc": "2.0", "id": i, "method": "tools/list"}, headers=headers).status_code for i in range(4)]

    assert statuses[:2] == [200, 200]
    assert statuses[2:] == [429, 429]

    audited = db.execute(select(ExternalMCPCall).where(ExternalMCPCall.token_id == token.id)).scalars().all()
    assert sorted(row.status_code for row in audited) == [200, 200, 429, 429]


def test_revoked_token_is_rejected(tmp_path, monkeypatch):
    from app.services.mcp_token_service import revoke_token

    app, session_factory = build_test_app(monkeypatch, tmp_path)
    db = session_factory()
    token, raw = create_token(db, name="Departing Partner")
    revoke_token(db, token.id)

    with TestClient(app) as client:
        response = client.post("/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers={"Authorization": f"Bearer {raw}"})
    assert response.status_code == 401
