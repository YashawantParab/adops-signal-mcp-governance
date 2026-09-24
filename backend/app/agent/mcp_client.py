from __future__ import annotations

import asyncio
import json
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, get_default_environment, stdio_client

from app.config import Settings, get_settings

# backend/app/agent/mcp_client.py -> backend/app -> backend -> <repo root>
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MCP_SERVER_DIR = REPO_ROOT / "mcp-server"


class MCPClientError(RuntimeError):
    """Raised for any MCP transport/protocol failure: subprocess start, timeout,
    initialize failure, or a malformed tool result. Callers never see the raw
    mcp SDK exception type - this is the one error type the agent runtime
    needs to know how to classify for `fallback_reason`.
    """


@dataclass(frozen=True)
class MCPToolInfo:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class MCPCallResult:
    ok: bool
    data: dict[str, Any]
    is_error: bool
    raw_text: str | None = None


class MCPAgentClient:
    """A real MCP client, over stdio, to this project's own standalone MCP server.

    One instance = one subprocess + one protocol session, scoped to a single
    agent run. Must be used as an async context manager so the subprocess is
    always torn down, including on error, timeout, or cancellation:

        async with MCPAgentClient() as client:
            tools = await client.list_tools()
            result = await client.call_tool("get_campaign_health", {"campaign_id": 1045})
    """

    def __init__(self, settings: Settings | None = None, *, extra_env: dict[str, str] | None = None) -> None:
        self._settings = settings or get_settings()
        self._extra_env = extra_env or {}
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "MCPAgentClient":
        self._exit_stack = AsyncExitStack()
        server_dir = Path(self._settings.mcp_server_cwd) if self._settings.mcp_server_cwd else DEFAULT_MCP_SERVER_DIR
        command_parts = [self._settings.mcp_server_command or sys.executable]
        args = (self._settings.mcp_server_args or "-m adops_signal_mcp.server").split()

        params = StdioServerParameters(
            command=command_parts[0],
            args=command_parts[1:] + args,
            cwd=str(server_dir),
            # get_default_environment() only inherits a safe OS allowlist (PATH, HOME, ...)
            # - it deliberately does NOT include DATABASE_URL, so without setting it
            # explicitly here the mcp-server subprocess would silently fall back to its
            # own default sqlite path instead of this deployment's real database.
            env={
                **get_default_environment(),
                "MCP_TRANSPORT": "stdio",
                "DATABASE_URL": self._settings.database_url,
                **self._extra_env,
            },
        )
        try:
            read_stream, write_stream = await self._exit_stack.enter_async_context(stdio_client(params))
            session = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await asyncio.wait_for(session.initialize(), timeout=self._settings.agent_timeout_seconds)
        except Exception as exc:
            await self._exit_stack.aclose()
            self._exit_stack = None
            raise MCPClientError(f"Could not start or initialize the MCP server: {exc}") from exc
        self._session = session
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
        self._session = None
        self._exit_stack = None

    async def list_tools(self) -> list[MCPToolInfo]:
        if self._session is None:
            raise MCPClientError("MCP session is not initialized")
        try:
            result = await asyncio.wait_for(self._session.list_tools(), timeout=self._settings.agent_timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise MCPClientError("Timed out listing MCP tools") from exc
        except Exception as exc:
            raise MCPClientError(f"Failed to list MCP tools: {exc}") from exc
        return [
            MCPToolInfo(name=tool.name, description=tool.description or "", input_schema=tool.inputSchema or {})
            for tool in result.tools
        ]

    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, timeout_seconds: float | None = None
    ) -> MCPCallResult:
        if self._session is None:
            raise MCPClientError("MCP session is not initialized")
        try:
            result = await asyncio.wait_for(
                self._session.call_tool(name, arguments),
                timeout=timeout_seconds or self._settings.agent_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise MCPClientError(f"MCP tool call '{name}' timed out") from exc
        except Exception as exc:
            raise MCPClientError(f"MCP tool call '{name}' failed: {exc}") from exc

        data, raw_text = _parse_tool_result(result)
        return MCPCallResult(ok=bool(data.get("ok", not result.isError)), data=data, is_error=bool(result.isError), raw_text=raw_text)


def _parse_tool_result(result: Any) -> tuple[dict[str, Any], str | None]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured, None

    text_blocks = [block.text for block in result.content if getattr(block, "type", None) == "text"]
    raw_text = "\n".join(text_blocks) if text_blocks else None
    if raw_text:
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed, raw_text

    return (
        {"ok": False, "error": {"code": "MALFORMED_MCP_RESPONSE", "message": "MCP tool result was not a JSON object"}},
        raw_text,
    )
