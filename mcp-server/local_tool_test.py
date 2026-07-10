from __future__ import annotations

import json

from adops_signal_mcp.tools import get_campaign_health, ping_adops_signal


def main() -> None:
    print(json.dumps(ping_adops_signal(), indent=2))
    print(json.dumps(get_campaign_health(1045), indent=2))


if __name__ == "__main__":
    main()

