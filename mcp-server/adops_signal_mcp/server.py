from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from adops_signal_mcp.tools import get_brand_safety_findings as get_brand_safety_findings_impl
from adops_signal_mcp.tools import get_campaign_health as get_campaign_health_impl
from adops_signal_mcp.tools import get_campaign_pacing as get_campaign_pacing_impl
from adops_signal_mcp.tools import get_recommendation_history as get_recommendation_history_impl
from adops_signal_mcp.tools import get_vast_validation_summary as get_vast_validation_summary_impl
from adops_signal_mcp.tools import ping_adops_signal as ping_adops_signal_impl
from adops_signal_mcp.tools import search_policy_context as search_policy_context_impl


mcp = FastMCP("SignalOps AI MCP Governance", json_response=True)


@mcp.tool()
def ping_adops_signal() -> dict[str, Any]:
    """Check whether the SignalOps AI MCP server can reach the AdOps data store."""
    return ping_adops_signal_impl()


@mcp.tool()
def get_campaign_health(campaign_id: int) -> dict[str, Any]:
    """Get structured health, pacing, creative, inventory, and bid signals for one campaign."""
    return get_campaign_health_impl(campaign_id)


@mcp.tool()
def get_campaign_pacing(campaign_id: int) -> dict[str, Any]:
    """Get latest and historical pacing snapshots for one campaign."""
    return get_campaign_pacing_impl(campaign_id)


@mcp.tool()
def get_vast_validation_summary(campaign_id: int) -> dict[str, Any]:
    """Get creative approval and VAST validation summary for one campaign."""
    return get_vast_validation_summary_impl(campaign_id)


@mcp.tool()
def get_brand_safety_findings(campaign_id: int) -> dict[str, Any]:
    """Get deterministic brand-safety governance findings for one campaign."""
    return get_brand_safety_findings_impl(campaign_id)


@mcp.tool()
def get_recommendation_history(campaign_id: int) -> dict[str, Any]:
    """Get recommendation history and human decision metadata for one campaign."""
    return get_recommendation_history_impl(campaign_id)


@mcp.tool()
def search_policy_context(query: str) -> dict[str, Any]:
    """Search local governance policy markdown using keyword retrieval."""
    return search_policy_context_impl(query)


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
