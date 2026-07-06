from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolDescriptor:
    """Describes one bounded agent tool in an MCP-compatible shape.

    This is a descriptor registry, not a running protocol server: it exists so the
    agent's tool surface is enumerable and documented in the same shape an MCP tool
    listing would use (name, description, input schema, output contract). A real MCP
    server would wrap these same functions from app.agent.tools behind this metadata;
    see docs/AI_AGENT_DESIGN.md for when that would be worth adding.
    """

    name: str
    description: str
    input_schema: dict
    output_contract: str


_CAMPAIGN_INPUT_SCHEMA = {
    "type": "object",
    "properties": {"campaign_id": {"type": "integer", "description": "Campaign primary key"}},
    "required": ["campaign_id"],
}

TOOL_REGISTRY: list[ToolDescriptor] = [
    ToolDescriptor(
        name="campaign_summary_tool",
        description="Summarizes campaign identity, flight dates, delivery, and current risk level.",
        input_schema=_CAMPAIGN_INPUT_SCHEMA,
        output_contract="ToolResult(evidence: EvidenceItem[], payload: {status, priority_level, risk_level, pacing_percentage})",
    ),
    ToolDescriptor(
        name="campaign_pacing_tool",
        description="Compares actual vs. expected delivery from the latest pacing snapshot.",
        input_schema=_CAMPAIGN_INPUT_SCHEMA,
        output_contract="ToolResult(evidence: EvidenceItem[], payload: CampaignHealth)",
    ),
    ToolDescriptor(
        name="campaign_setup_tool",
        description="Checks frequency cap and launch-date lag against the campaign flight.",
        input_schema=_CAMPAIGN_INPUT_SCHEMA,
        output_contract="ToolResult(evidence: EvidenceItem[], payload: {frequency_cap, launch_lag_days})",
    ),
    ToolDescriptor(
        name="targeting_analyzer_tool",
        description="Computes eligible inventory percentage against country/device/category targeting.",
        input_schema=_CAMPAIGN_INPUT_SCHEMA,
        output_contract="ToolResult(evidence: EvidenceItem[], payload: InventorySummary)",
    ),
    ToolDescriptor(
        name="inventory_checker_tool",
        description="Aggregates ad-request failure rate and the dominant failure reason.",
        input_schema=_CAMPAIGN_INPUT_SCHEMA,
        output_contract="ToolResult(evidence: EvidenceItem[], payload: {failure_rate, top_failure_reason, failure_reasons})",
    ),
    ToolDescriptor(
        name="portfolio_inventory_pressure_tool",
        description="Detects shared-inventory contention with other active high-priority campaigns.",
        input_schema=_CAMPAIGN_INPUT_SCHEMA,
        output_contract="ToolResult(evidence: EvidenceItem[], payload: {affected_request_count, high_priority_campaign_ids})",
    ),
    ToolDescriptor(
        name="vast_validation_tool",
        description="Checks creative approval status and VAST validation error counts.",
        input_schema=_CAMPAIGN_INPUT_SCHEMA,
        output_contract="ToolResult(evidence: EvidenceItem[], payload: {rejected_count, error_count, error_codes})",
    ),
    ToolDescriptor(
        name="sql_analysis_tool",
        description="Analyzes bid win rate and below-floor rate from recorded auction responses.",
        input_schema=_CAMPAIGN_INPUT_SCHEMA,
        output_contract="ToolResult(evidence: EvidenceItem[], payload: BidSummary)",
    ),
    ToolDescriptor(
        name="goal_feasibility_tool",
        description="Forecasts whether the campaign can reach its goal by a target date at the current run rate.",
        input_schema={
            **_CAMPAIGN_INPUT_SCHEMA,
            "properties": {
                **_CAMPAIGN_INPUT_SCHEMA["properties"],
                "query": {"type": "string", "description": "Operator question, used to infer a target date"},
            },
        },
        output_contract="ToolResult(evidence: EvidenceItem[], payload: {required_daily, recent_daily, feasible, projected_gap})",
    ),
    ToolDescriptor(
        name="rag_documentation_lookup",
        description="Retrieves the most similar AdOps playbook sections for the operator's question via vector search.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Operator question or diagnosis text"}},
            "required": ["query"],
        },
        output_contract="ToolResult(evidence: EvidenceItem[], payload: {docs: PlaybookSource[]})",
    ),
]


def list_tools() -> list[ToolDescriptor]:
    return list(TOOL_REGISTRY)
