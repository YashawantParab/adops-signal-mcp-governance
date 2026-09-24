"""The single choke point every MCP tool call the governed agent makes must pass
through. No tool result may reach the LLM without first passing through
`governed_tool_call` - there is no other path from the agent runtime to MCP.

Order enforced here, matching the product governance model:
  agent proposes tool
    -> tool registry validation      (does this tool exist?)
    -> permission check              (is it read-only / granted?)
    -> scope/policy check            (is it scoped to this run's campaign?)
    -> create/log pending tool call  (audit row exists before execution)
    -> MCP call                      (the real stdio MCP round trip)
    -> record latency/result/error   (update the same row - success or failure)
    -> return a normalized outcome   (the agent runtime turns this into evidence)

A denied call (unknown tool, permission, or scope) is logged exactly like a
failed MCP call - never silently dropped - and its result is never executed.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.agent.mcp_client import MCPAgentClient, MCPClientError
from app.models import MCPToolCall
from app.services.mcp_governance_service import MCP_TOOL_DESCRIPTORS

READ_ONLY_PERMISSION = "read"

_TOOL_DESCRIPTOR_BY_NAME = {descriptor.name: descriptor for descriptor in MCP_TOOL_DESCRIPTORS}


class GovernanceDenied(RuntimeError):
    """Raised when a proposed tool call is rejected before it ever reaches MCP.

    `reason_code` is one of: UNKNOWN_TOOL, PERMISSION_DENIED, OUT_OF_SCOPE.
    """

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class GovernedToolOutcome:
    tool_name: str
    ok: bool
    data: dict[str, Any]
    latency_ms: int
    error_category: str | None
    tool_call_id: int


def validate_tool_call(tool_name: str, arguments: dict[str, Any], *, scoped_campaign_id: int) -> None:
    """Registry validation + permission check + investigation-scope check.

    Raises GovernanceDenied on the first failing check. Pure and synchronous
    on purpose: it never touches the DB or MCP, so it is trivially unit
    testable and always runs before any side effect.
    """
    descriptor = _TOOL_DESCRIPTOR_BY_NAME.get(tool_name)
    if descriptor is None:
        raise GovernanceDenied("UNKNOWN_TOOL", f"'{tool_name}' is not a registered MCP tool")

    if descriptor.permission_level != READ_ONLY_PERMISSION:
        raise GovernanceDenied(
            "PERMISSION_DENIED",
            f"'{tool_name}' requires permission level '{descriptor.permission_level}', which this agent is not granted",
        )

    campaign_id = arguments.get("campaign_id")
    if campaign_id is not None and int(campaign_id) != scoped_campaign_id:
        raise GovernanceDenied(
            "OUT_OF_SCOPE",
            f"'{tool_name}' targeted campaign {campaign_id}, but this investigation is scoped to campaign {scoped_campaign_id}",
        )


async def governed_tool_call(
    db: Session,
    *,
    agent_run_id: int,
    mcp_client: MCPAgentClient,
    tool_name: str,
    arguments: dict[str, Any],
    scoped_campaign_id: int,
) -> GovernedToolOutcome:
    pending = MCPToolCall(
        agent_run_id=agent_run_id,
        tool_name=tool_name,
        input_json=arguments,
        output_json={},
        status="pending",
        latency_ms=0,
    )
    db.add(pending)
    db.flush()

    started = time.perf_counter()

    try:
        validate_tool_call(tool_name, arguments, scoped_campaign_id=scoped_campaign_id)
    except GovernanceDenied as exc:
        return _finalize(
            db,
            pending,
            started,
            data={"ok": False, "error": {"code": exc.reason_code, "message": str(exc)}},
            status="denied",
            error_category=exc.reason_code,
        )

    try:
        result = await mcp_client.call_tool(tool_name, arguments)
    except MCPClientError as exc:
        return _finalize(
            db,
            pending,
            started,
            data={"ok": False, "error": {"code": "MCP_CALL_FAILED", "message": str(exc)}},
            status="failed",
            error_category="MCP_CALL_FAILED",
        )

    if result.ok:
        return _finalize(db, pending, started, data=result.data, status="success", error_category=None)

    error_category = str(result.data.get("error", {}).get("code", "TOOL_ERROR"))
    return _finalize(db, pending, started, data=result.data, status="failed", error_category=error_category)


def _finalize(
    db: Session,
    pending: MCPToolCall,
    started: float,
    *,
    data: dict[str, Any],
    status: str,
    error_category: str | None,
) -> GovernedToolOutcome:
    latency_ms = max(int((time.perf_counter() - started) * 1000), 1)
    pending.output_json = data
    pending.status = status
    pending.latency_ms = latency_ms
    pending.error_category = error_category
    db.add(pending)
    db.flush()
    return GovernedToolOutcome(
        tool_name=pending.tool_name,
        ok=status == "success",
        data=data,
        latency_ms=latency_ms,
        error_category=error_category,
        tool_call_id=pending.id,
    )
