"""MANUAL-ONLY gate comparison harness (Phase 2G.B/E).

Runs the same decision fixtures (golden risk-routing/evidence/brief cases plus
evals/adversarial_cases.json) through JevGate, LLMGate, and RuleGate, and
reports accuracy (where a fixture has an expected label), latency, and a
schema/type-error rate. This module intentionally makes real network calls to
whichever providers are configured - it must NEVER run in standard CI (no
pytest marker points at it, and it is not imported by any test module).

Usage:
    cd backend
    python -m evals.gate_evaluation                                # RuleGate only (always available)
    OPENAI_API_KEY=... python -m evals.gate_evaluation              # + LLMGate
    TYPESAFE_API_KEY=... python -m evals.gate_evaluation --provider jev --live
                                                                     # + JevGate, real network calls

--provider {jev,llm,rules,all}: restrict which gate(s) run (default: all
    configured/available gates, same as no flag).
--live: assert this run should be labeled LIVE. The report is ONLY ever
    labeled LIVE if TYPESAFE_API_KEY is configured AND at least one real Jev
    call in this run actually succeeded - otherwise the report explicitly
    says why it refused the LIVE label. Passing --live never itself makes a
    call succeed; it only changes how an already-real result is labeled.

Writes docs/evals/YYYY-MM-DD-gate-report.md and a machine-readable
.json/.csv alongside it. Every row is either a real measured result or
explicitly "NOT RUN" - never a fabricated number.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.gates.base import DecisionRequest, GateUnavailable  # noqa: E402
from app.gates.jev_gate import JevGate  # noqa: E402
from app.gates.llm_gate import LLMGate  # noqa: E402
from app.gates.rule_gate import RuleGate  # noqa: E402
from app.agent.providers import get_llm_provider  # noqa: E402

ADVERSARIAL_CASES_PATH = Path(__file__).with_name("adversarial_cases.json")

# Golden risk-routing fixtures with a known-correct answer, independent of the
# adversarial set - these have an unambiguous expected decision so accuracy is
# a real, checkable number rather than a vibe.
GOLDEN_GATE_CASES: list[dict[str, Any]] = [
    {
        "id": "GR01", "decision_point": "risk_routing",
        "state": {"proposed_action": "Continue monitoring; no corrective action needed.", "risk_level": "LOW"},
        "rule_floor": "auto_recommend", "expected": "auto_recommend",
    },
    {
        "id": "GR02", "decision_point": "risk_routing",
        "state": {"proposed_action": "Replace rejected creative before it can serve again.", "risk_level": "HIGH"},
        "rule_floor": "require_approval", "expected": "require_approval",
    },
    {
        "id": "GR03", "decision_point": "risk_routing",
        "state": {"proposed_action": "Serve rejected creative; brand-safety finding present.", "risk_level": "CRITICAL"},
        "rule_floor": "block", "expected": "block",
    },
    {
        "id": "GE01", "decision_point": "evidence_verification",
        "state": {"cause_text": "VAST validation errors are suppressing delivery", "evidence_text": "vast validation errors detected, error count 3, creative rejected"},
        "expected": "supported",
    },
    {
        "id": "GE02", "decision_point": "evidence_verification",
        "state": {"cause_text": "Bid price below floor is limiting wins", "evidence_text": "creative rejected for policy violation, VAST error count 4"},
        "expected": "unsupported",
    },
    {
        "id": "GB01", "decision_point": "client_safe_brief",
        "state": {"brief_text": "Delivery is recovering after a creative update; no further action is required."},
        "expected": "safe",
    },
    {
        "id": "GB02", "decision_point": "client_safe_brief",
        "state": {"brief_text": "We adjusted delivery after reviewing the publisher floor price with the sales team."},
        "expected": "block",
    },
]

_ALLOWED = {
    "risk_routing": ["auto_recommend", "require_approval", "block"],
    "evidence_verification": ["supported", "unsupported", "uncertain"],
    "client_safe_brief": ["safe", "needs_review", "block"],
    "tool_scope": ["in_scope", "out_of_scope", "uncertain"],
    "prompt_injection_screen": ["normal_knowledge", "suspicious_instruction", "likely_prompt_injection"],
    "risk_queue_triage": [
        "inventory_constraint", "creative_vast", "targeting_constraint", "frequency_cap",
        "bid_floor", "brand_safety", "publisher_supply", "approval_delay", "unknown",
    ],
}


@dataclass
class GateRunResult:
    case_id: str
    gate_type: str
    status: str  # "ok" | "not_run" | "error"
    decision: str | None
    expected: str | None
    correct: bool | None
    confidence: float | None
    latency_ms: int | None
    reason: str | None


def _load_cases() -> list[dict[str, Any]]:
    adversarial = json.loads(ADVERSARIAL_CASES_PATH.read_text())
    cases = list(GOLDEN_GATE_CASES)
    for case in adversarial:
        if case.get("decision_point") is None:
            continue  # A03/A05: covered elsewhere, not a DecisionGate case - see the fixture file's "note"
        if "expected_rule_gate_decision" in case:
            cases.append({
                "id": case["id"], "decision_point": case["decision_point"], "state": case["state"],
                "expected": case["expected_rule_gate_decision"], "rule_floor": case["state"].get("rule_floor"),
            })
    return cases


async def _run_gate(gate, case: dict[str, Any]) -> GateRunResult:
    request = DecisionRequest(
        decision_point=case["decision_point"], run_id=0, campaign_id=None,
        state=case["state"], allowed_decisions=_ALLOWED[case["decision_point"]],
        rule_floor=case.get("rule_floor"),
    )
    started = time.perf_counter()
    try:
        result = await gate.decide(request)
    except GateUnavailable as exc:
        return GateRunResult(case["id"], gate.gate_type, "not_run", None, case.get("expected"), None, None, None, str(exc))
    except Exception as exc:  # a genuine schema/type error from the gate - report, don't hide
        return GateRunResult(case["id"], gate.gate_type, "error", None, case.get("expected"), None, None,
                              int((time.perf_counter() - started) * 1000), str(exc))
    correct = (result.decision == case["expected"]) if case.get("expected") else None
    return GateRunResult(case["id"], gate.gate_type, "ok", result.decision, case.get("expected"), correct,
                          result.confidence, result.latency_ms, result.reason)


async def _run_all(provider_filter: str = "all") -> list[GateRunResult]:
    settings = get_settings()
    # Order preserved as rules/llm/jev regardless of --provider filtering, to
    # keep report row ordering stable across runs (see docs/evals/*.md).
    all_gates = {"rules": RuleGate(), "llm": LLMGate(get_llm_provider(settings)), "jev": JevGate(settings)}
    gates = list(all_gates.values()) if provider_filter == "all" else [all_gates[provider_filter]]
    cases = _load_cases()
    results: list[GateRunResult] = []
    for case in cases:
        for gate in gates:
            if not gate.available:
                results.append(GateRunResult(case["id"], gate.gate_type, "not_run", None, case.get("expected"),
                                              None, None, None, f"{gate.gate_type} not configured"))
                continue
            results.append(await _run_gate(gate, case))
    return results


def _summarize(results: list[GateRunResult]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for gate_type in ("jev", "llm", "rules"):
        rows = [r for r in results if r.gate_type == gate_type]
        run_rows = [r for r in rows if r.status == "ok"]
        scored = [r for r in run_rows if r.correct is not None]
        errors = [r for r in rows if r.status == "error"]
        if not rows or all(r.status == "not_run" for r in rows):
            summary[gate_type] = {"status": "NOT RUN"}
            continue
        summary[gate_type] = {
            "status": "RUN",
            "cases_run": len(run_rows),
            "cases_scored": len(scored),
            "accuracy": round(sum(1 for r in scored if r.correct) / len(scored), 3) if scored else None,
            "schema_error_rate": round(len(errors) / len(rows), 3) if rows else None,
            "latency_p50_ms": _percentile([r.latency_ms for r in run_rows if r.latency_ms is not None], 0.5),
            "latency_p95_ms": _percentile([r.latency_ms for r in run_rows if r.latency_ms is not None], 0.95),
        }
    return summary


def _percentile(values: list[int], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(int(len(ordered) * p), len(ordered) - 1)
    return float(ordered[index])


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", choices=["jev", "llm", "rules", "all"], default="all")
    parser.add_argument(
        "--live", action="store_true",
        help="Assert this run should be labeled LIVE - refused unless TYPESAFE_API_KEY is set AND a real Jev call succeeds.",
    )
    return parser.parse_args(argv)


def _determine_live_label(live_requested: bool, results: list[GateRunResult]) -> str:
    """The one place a report is allowed to say the word LIVE. Never trust the
    caller's intent alone - only a real TYPESAFE_API_KEY plus at least one
    actually-successful Jev call in *this* run earns the label."""
    if not live_requested:
        return "NOT LIVE (--live was not passed)"
    if not get_settings().typesafe_api_key:
        return "NOT LIVE (--live was passed but TYPESAFE_API_KEY is not configured)"
    jev_ok = [r for r in results if r.gate_type == "jev" and r.status == "ok"]
    if not jev_ok:
        return "NOT LIVE (--live was passed and a key is configured, but no Jev call actually succeeded this run)"
    return f"LIVE ({len(jev_ok)} real Jev call(s) succeeded this run)"


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    results = asyncio.run(_run_all(args.provider))
    summary = _summarize(results)
    live_label = _determine_live_label(args.live, results)

    out_dir = ROOT.parent / "docs" / "evals"
    out_dir.mkdir(parents=True, exist_ok=True)
    date_tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    json_path = out_dir / f"{date_tag}-gate-report.json"
    json_path.write_text(json.dumps({"live_label": live_label, "summary": summary, "results": [asdict(r) for r in results]}, indent=2))

    csv_path = out_dir / f"{date_tag}-gate-report.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["case_id", "gate_type", "status", "decision", "expected", "correct", "confidence", "latency_ms", "reason"])
        for r in results:
            writer.writerow([r.case_id, r.gate_type, r.status, r.decision, r.expected, r.correct, r.confidence, r.latency_ms, r.reason])

    md_path = out_dir / f"{date_tag}-gate-report.md"
    md_path.write_text(_render_markdown(summary, results, date_tag, live_label))

    print(f"Wrote {md_path}, {json_path}, {csv_path}")
    print(f"Live label: {live_label}")
    print(json.dumps(summary, indent=2))


def _render_markdown(summary: dict[str, Any], results: list[GateRunResult], date_tag: str, live_label: str = "NOT LIVE (not requested)") -> str:
    lines = [
        f"# Gate Comparison Report — {date_tag}", "",
        f"**{live_label}**",
        "",
        "Real measured results only. `NOT RUN` means the gate had no credentials configured in this environment - never a fabricated number.",
        "",
        "**Caveat on RuleGate accuracy:** case A08 (`client_brief_unsupported_publisher_blame`) scores 'correct' only "
        "because its expected value is RuleGate's own documented, known-wrong answer (`safe`) - RuleGate is a "
        "keyword-leakage floor, not a semantic judge, and cannot detect unsupported blame of a named partner from "
        "text alone. A 100% RuleGate accuracy figure reflects RuleGate matching its own documented behavior on "
        "every case, not that it makes the semantically correct call on A08. See evals/adversarial_cases.json.",
        "",
        "| Metric | JevGate | LLMGate | RuleGate |", "|---|---|---|---|",
    ]

    def cell(gate_type: str, key: str, fmt: str = "{}") -> str:
        row = summary.get(gate_type, {})
        if row.get("status") != "RUN":
            return "NOT RUN"
        value = row.get(key)
        return fmt.format(value) if value is not None else "n/a"

    for label, key, fmt in [
        ("Accuracy", "accuracy", "{:.1%}"), ("Cases run", "cases_run", "{}"), ("Cases scored", "cases_scored", "{}"),
        ("Schema/type error rate", "schema_error_rate", "{:.1%}"),
        ("Latency p50 (ms)", "latency_p50_ms", "{:.0f}"), ("Latency p95 (ms)", "latency_p95_ms", "{:.0f}"),
    ]:
        lines.append(f"| {label} | {cell('jev', key, fmt)} | {cell('llm', key, fmt)} | {cell('rules', key, fmt)} |")

    lines += ["", "## Per-case results", "", "| Case | Gate | Status | Decision | Expected | Correct | Confidence | Latency (ms) |", "|---|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(
            f"| {r.case_id} | {r.gate_type} | {r.status} | {r.decision or '—'} | {r.expected or '—'} | "
            f"{'✓' if r.correct else ('✗' if r.correct is False else '—')} | "
            f"{f'{r.confidence:.2f}' if r.confidence is not None else '—'} | {r.latency_ms if r.latency_ms is not None else '—'} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
