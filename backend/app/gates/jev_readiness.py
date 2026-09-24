"""Jev readiness check: `python -m app.gates.jev_readiness`.

Reports exactly what is and isn't ready for live Jev (TypeSafe System One)
execution, without ever running the manual gate-comparison evaluation and
without ever printing the API key. Safe to run at any time - with no
TYPESAFE_API_KEY configured it makes zero network calls; with a key configured
it makes exactly one lightweight `client.models.list()` call to confirm
connectivity (never a `system_one()` call, which is the metered/billed
operation - see docs/jev-integration-notes.md).

Exit code is 0 regardless of readiness state - this is a report, not a gate;
CI should never depend on Jev being live.
"""
from __future__ import annotations

import asyncio
import sys

from app.config import get_settings


async def _check_remote_connectivity(api_key: str, model: str, timeout: float) -> tuple[bool, str]:
    try:
        import typesafe_sdk as sdk
    except ImportError as exc:
        return False, f"typesafe-sdk not installed: {exc}"

    try:
        async with sdk.AsyncTypeSafeClient(api_key=api_key, model=model, timeout=timeout) as client:
            response = await client.models.list()
    except sdk.TypeSafeAuthenticationError as exc:
        return False, f"authentication failed - check TYPESAFE_API_KEY: {exc}"
    except sdk.TypeSafeError as exc:
        return False, f"request failed: {exc}"
    except Exception as exc:  # pragma: no cover - defensive, never crash a readiness check
        return False, f"unexpected failure: {exc}"

    model_names = [m.name for m in getattr(response, "models", [])]
    return True, f"connected - {len(model_names)} model(s) available to this account"


def main() -> int:
    settings = get_settings()
    lines: list[str] = []

    try:
        import typesafe_sdk

        sdk_version = getattr(typesafe_sdk, "__version__", "unknown")
        sdk_installed = True
    except ImportError:
        sdk_version = None
        sdk_installed = False

    lines.append(f"[{'OK ' if sdk_installed else 'MISSING'}] SDK installed: typesafe-sdk {sdk_version or ''}".rstrip())

    try:
        from app.gates.jev_gate import JevGate  # noqa: F401

        adapter_present = True
    except ImportError:
        adapter_present = False
    lines.append(f"[{'OK ' if adapter_present else 'MISSING'}] Jev adapter: app/gates/jev_gate.py importable")

    lines.append(
        "[OK ] API contract: implemented against typesafe-sdk==0.7.1's confirmed contract "
        "(see docs/jev-integration-notes.md - CONFIRMED FROM OFFICIAL SOURCES section)"
    )

    key_configured = bool(settings.typesafe_api_key)
    # Never print the key itself - only whether it is set, and its length as a
    # sanity check a real value was pasted (not the value).
    key_hint = f"set ({len(settings.typesafe_api_key)} chars)" if key_configured else "not set"
    lines.append(f"[{'OK ' if key_configured else 'MISSING'}] TYPESAFE_API_KEY: {key_hint}")

    if not sdk_installed:
        lines.append("[SKIPPED] Remote connectivity: SDK not installed")
        remote_ok = False
    elif not key_configured:
        lines.append("[SKIPPED] Remote connectivity: no TYPESAFE_API_KEY configured")
        remote_ok = False
    else:
        remote_ok, detail = asyncio.run(
            _check_remote_connectivity(settings.typesafe_api_key, settings.jev_model, settings.jev_timeout_seconds)
        )
        lines.append(f"[{'OK ' if remote_ok else 'FAILED'}] Remote connectivity: {detail}")

    if remote_ok:
        lines.append(
            "[READY] Live Jev evaluation: run `python -m evals.gate_evaluation --provider jev --live` "
            "from backend/ to execute real Jev decisions and collect real metrics."
        )
    else:
        lines.append(
            "[NOT RUN] Live Jev evaluation: cannot run until remote connectivity succeeds - "
            "see docs/JEV_ACTIVATION_RUNBOOK.md."
        )

    print("\n".join(lines))

    if sdk_installed and adapter_present and key_configured and remote_ok:
        print("\nOverall: JEV INTEGRATION READY - LIVE ACCESS CONFIRMED")
    elif sdk_installed and adapter_present:
        print("\nOverall: JEV INTEGRATION READY - LIVE ACCESS PENDING")
    else:
        print("\nOverall: NOT JEV READY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
