"""Hosted, authenticated, read-only external MCP endpoint (Phase 3F).

Mounts the SAME FastMCP instance the internal governed agent talks to over
stdio (mcp-server/adops_signal_mcp/server.py) - no separate tool
implementation, no risk of the two surfaces diverging. Every request is
authenticated against app.services.mcp_token_service, rate-limited per
token, and audited to external_mcp_calls BEFORE it reaches the MCP session
manager. Read-only by construction: this FastMCP instance declares no write
tools (see docs/mcp-tool-registry.md) - there is nothing an external client
could call that mutates anything, and none of this project's write endpoints
(actions, approvals, agent runs) are reachable through it.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings
from app.database import SessionLocal
from app.models import ExternalMCPCall
from app.rate_limit import check_rate_limit
from app.services.mcp_token_service import verify_token

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_SERVER_DIR = REPO_ROOT / "mcp-server"
EXTERNAL_MCP_MOUNT_PATH = "/mcp/external"


def _load_fastmcp_instance() -> Any:
    path = str(MCP_SERVER_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    from adops_signal_mcp.server import mcp as fastmcp_instance  # noqa: PLC0415

    return fastmcp_instance


def _audit(
    *, token_id: int | None, method: str, tool_name: str | None,
    status_code: int, latency_ms: int, client_host: str | None,
) -> None:
    with SessionLocal() as db:
        db.add(
            ExternalMCPCall(
                token_id=token_id, method=method, tool_name=tool_name,
                status_code=status_code, latency_ms=latency_ms, client_host=client_host,
            )
        )
        db.commit()


async def _peek_jsonrpc_method(request: Request) -> tuple[str, str | None]:
    """Reads the JSON-RPC envelope to log which MCP method/tool was called.
    Starlette caches request.body() internally, so the downstream MCP session
    manager can still read the full body afterward - this never consumes it."""
    try:
        body = await request.body()
        payload = json.loads(body)
        method = str(payload.get("method", "unknown"))
        tool_name = payload.get("params", {}).get("name") if method == "tools/call" else None
        return method, tool_name
    except Exception:
        return "unparsed", None


class ExternalMCPAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_host = request.client.host if request.client else None
        auth_header = request.headers.get("authorization", "")
        raw_token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""

        with SessionLocal() as db:
            token = verify_token(db, raw_token)
        if token is None:
            _audit(token_id=None, method="unauthenticated", tool_name=None, status_code=401, latency_ms=0, client_host=client_host)
            return JSONResponse({"error": "invalid or missing bearer token"}, status_code=401)

        token_id, rate_limit = token.id, token.rate_limit_per_minute
        if not check_rate_limit(f"external-mcp-token:{token_id}", rate_limit):
            _audit(token_id=token_id, method="rate_limited", tool_name=None, status_code=429, latency_ms=0, client_host=client_host)
            return JSONResponse({"error": "rate limit exceeded"}, status_code=429)

        method, tool_name = await _peek_jsonrpc_method(request)
        started = time.perf_counter()
        response = await call_next(request)
        latency_ms = int((time.perf_counter() - started) * 1000)

        _audit(token_id=token_id, method=method, tool_name=tool_name, status_code=response.status_code, latency_ms=latency_ms, client_host=client_host)
        return response


def build_hosted_mcp_app() -> tuple[Starlette, Any]:
    """Returns (mounted_app, fastmcp_instance). The caller (app.main) owns
    entering/exiting fastmcp_instance.session_manager.run() across its own
    startup/shutdown - see FastMCP.session_manager's docstring for why this
    is the documented pattern for mounting into an existing FastAPI app."""
    fastmcp_instance = _load_fastmcp_instance()
    # Without this, streamable_http_app() registers its own internal route at
    # the SDK's default "/mcp", which would compose with our mount prefix into
    # a doubled path (EXTERNAL_MCP_MOUNT_PATH + "/mcp") instead of exactly
    # EXTERNAL_MCP_MOUNT_PATH.
    fastmcp_instance.settings.streamable_http_path = "/"

    extra_hosts = [h.strip() for h in get_settings().external_mcp_allowed_hosts.split(",") if h.strip()]
    if extra_hosts:
        security = fastmcp_instance.settings.transport_security
        security.allowed_hosts = list({*security.allowed_hosts, *extra_hosts})
        security.allowed_origins = list({*security.allowed_origins, *[f"https://{h}" for h in extra_hosts]})

    inner_app = fastmcp_instance.streamable_http_app()  # creates _session_manager as a side effect
    inner_app.add_middleware(ExternalMCPAuthMiddleware)
    return inner_app, fastmcp_instance
