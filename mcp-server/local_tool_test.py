from __future__ import annotations

import json

from adops_signal_mcp.tools import (
    get_brand_safety_findings,
    get_campaign_health,
    get_campaign_pacing,
    get_recommendation_history,
    get_vast_validation_summary,
    ping_adops_signal,
    search_policy_context,
)


def main() -> None:
    payloads = [
        ping_adops_signal(),
        get_campaign_health(1045),
        get_campaign_pacing(1045),
        get_vast_validation_summary(1046),
        get_brand_safety_findings(1045),
        get_recommendation_history(1046),
        search_policy_context("budget shift human approval"),
    ]
    for payload in payloads:
        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
