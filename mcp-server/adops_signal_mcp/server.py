from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from adops_signal_mcp.tools import get_campaign_health as get_campaign_health_impl
from adops_signal_mcp.tools import ping_adops_signal as ping_adops_signal_impl


mcp = FastMCP("SignalOps AI MCP Governance", json_response=True)


@mcp.tool()
def ping_adops_signal() -> dict[str, Any]:
    """Check whether the SignalOps AI MCP server can reach the AdOps data store."""
    return ping_adops_signal_impl()


@mcp.tool()
def get_campaign_health(campaign_id: int) -> dict[str, Any]:
    """Get structured health, pacing, creative, inventory, and bid signals for one campaign."""
    return get_campaign_health_impl(campaign_id)


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()

