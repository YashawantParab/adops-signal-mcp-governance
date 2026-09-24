"""The MCP tool registry: one descriptor per tool this project's MCP server
exposes, and the source of truth both `governance_wrapper` (permission/scope
checks) and `mcp_governance_service` (the /api/mcp/tools listing) validate
against.

Kept in its own leaf module - importing nothing from `governance_wrapper`,
`mcp_agent_runtime`, or `mcp_governance_service` - so those three can import
this without forming a cycle.
"""
from __future__ import annotations

from app.schemas import MCPToolRead

MCP_TOOL_DESCRIPTORS = [
    MCPToolRead(
        name="ping_adops_signal",
        description="Checks MCP server and SignalOps AI data-store readiness.",
        read_only=True,
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_contract="Structured JSON readiness payload or typed error.",
        category="System",
        permission_level="read",
        risk_level="Low",
    ),
    MCPToolRead(
        name="get_campaign_health",
        description="Returns campaign health, pacing, inventory, creative, VAST, and bid summary.",
        read_only=True,
        input_schema={"type": "object", "properties": {"campaign_id": {"type": "integer", "minimum": 1}}},
        output_contract="Structured JSON campaign and health payload or typed error.",
        category="Campaign Signals",
        permission_level="read",
        risk_level="Low",
    ),
    MCPToolRead(
        name="get_campaign_pacing",
        description="Returns latest and historical pacing snapshots for one campaign.",
        read_only=True,
        input_schema={"type": "object", "properties": {"campaign_id": {"type": "integer", "minimum": 1}}},
        output_contract="Structured JSON pacing payload or typed error.",
        category="Campaign Signals",
        permission_level="read",
        risk_level="Low",
    ),
    MCPToolRead(
        name="get_vast_validation_summary",
        description="Summarizes creative approval state and persisted VAST validation errors.",
        read_only=True,
        input_schema={"type": "object", "properties": {"campaign_id": {"type": "integer", "minimum": 1}}},
        output_contract="Structured JSON VAST validation payload or typed error.",
        category="Creative Governance",
        permission_level="read",
        risk_level="Low",
    ),
    MCPToolRead(
        name="get_brand_safety_findings",
        description="Returns deterministic brand-safety governance findings from existing campaign data.",
        read_only=True,
        input_schema={"type": "object", "properties": {"campaign_id": {"type": "integer", "minimum": 1}}},
        output_contract="Structured JSON findings payload or typed error.",
        category="Brand Safety",
        permission_level="read",
        risk_level="Medium",
    ),
    MCPToolRead(
        name="get_recommendation_history",
        description="Returns recommendation history and reviewer metadata for one campaign.",
        read_only=True,
        input_schema={"type": "object", "properties": {"campaign_id": {"type": "integer", "minimum": 1}}},
        output_contract="Structured JSON recommendation history payload or typed error.",
        category="Governance History",
        permission_level="read",
        risk_level="Low",
    ),
    MCPToolRead(
        name="search_policy_context",
        description="Searches local governance policy markdown using keyword retrieval.",
        read_only=True,
        input_schema={"type": "object", "properties": {"query": {"type": "string", "minLength": 1}}},
        output_contract="Structured JSON policy matches or typed error.",
        category="Policy",
        permission_level="read",
        risk_level="Low",
    ),
]
