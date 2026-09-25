"""REAL, LIVE OpenAI LLMGate benchmark vs. RuleGate baseline.

MANUAL-ONLY - makes real, billed OpenAI API calls. Never runs in CI (no
pytest marker references it). Reuses the exact same fixtures as
evals/gate_evaluation.py (golden gate cases + the subset of
adversarial_cases.json with a decision_point/expected_rule_gate_decision) so
LLMGate and RuleGate are compared on identical inputs.

Runs each fixture through LLMGate REPEAT_RUNS times (default 3) to measure
decision consistency under real model stochasticity, and through RuleGate
once (RuleGate is deterministic - repeating it produces no new information).

Cost is CALCULATED (not MEASURED - the OpenAI Chat Completions API does not
return a dollar amount) from a pricing table populated only with rates
verified against OpenAI's published pricing on the date noted below. If the
configured model is not in the table, cost is reported as NOT AVAILABLE
rather than guessed.

Usage:
    cd backend
    python -m evals.openai_llmgate_benchmark
    python -m evals.openai_llmgate_benchmark --runs 3
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.providers import get_llm_provider  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.gates.base import DecisionRequest, GateUnavailable  # noqa: E402
from app.gates.llm_gate import LLMGate  # noqa: E402
from app.gates.rule_gate import RuleGate  # noqa: E402
from evals.gate_evaluation import _ALLOWED, _load_cases  # noqa: E402

# Verified 2026-09-25 against developers.openai.com/api/docs/pricing (Standard
# tier, per 1M tokens). Only models actually verified live are listed - an
# unlisted/unverified model must report cost as NOT AVAILABLE, never a guess.
OPENAI_PRICING_PER_1M_USD: dict[str, tuple[float, float]] = {
    "gpt-5.4-mini": (0.75, 4.50),
}


@dataclass
class RunRecord:
    case_id: str
    decision_point: str
    gate_type: str
    run_index: int
    status: str  # "ok" | "not_run" | "error"
    decision: str | None
    expected: str | None
    correct: bool | None
    confidence: float | None
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    error: str | None = None


async def _run_once(gate, case: dict[str, Any], run_index: int) -> RunRecord:
    allowed = _ALLOWED[case["decision_point"]]
    request = DecisionRequest(
        decision_point=case["decision_point"], run_id=0, campaign_id=None,
        state=case["state"], allowed_decisions=allowed, rule_floor=case.get("rule_floor"),
    )
    started = time.perf_counter()
    try:
        result = await gate.decide(request)
    except GateUnavailable as exc:
        return RunRecord(case["id"], case["decision_point"], gate.gate_type, run_index, "not_run",
                          None, case.get("expected"), None, None, None, None, None, str(exc))
    except Exception as exc:  # a genuine schema/type/parse error - report, never hide
        latency_ms = int((time.perf_counter() - started) * 1000)
        return RunRecord(case["id"], case["decision_point"], gate.gate_type, run_index, "error",
                          None, case.get("expected"), None, None, latency_ms, None, None, str(exc))
    correct = (result.decision == case["expected"]) if case.get("expected") else None
    return RunRecord(
        case["id"], case["decision_point"], gate.gate_type, run_index, "ok", result.decision,
        case.get("expected"), correct, result.confidence, result.latency_ms,
        result.metadata.get("input_tokens"), result.metadata.get("output_tokens"),
    )


async def _run_all(repeat_runs: int) -> list[RunRecord]:
    settings = get_settings()
    provider = get_llm_provider(settings)
    llm_gate = LLMGate(provider)
    rule_gate = RuleGate()
    cases = _load_cases()

    records: list[RunRecord] = []
    for case in cases:
        # RuleGate is deterministic - one run is the full signal.
        records.append(await _run_once(rule_gate, case, 1))
        for run_index in range(1, repeat_runs + 1):
            if not llm_gate.available:
                records.append(RunRecord(case["id"], case["decision_point"], "llm", run_index, "not_run",
                                          None, case.get("expected"), None, None, None, None, None,
                                          "LLM provider not configured"))
                continue
            records.append(await _run_once(llm_gate, case, run_index))
    return records


def _precision_recall_f1(records: list[RunRecord], classes: list[str]) -> dict[str, dict[str, float]]:
    """Per-class precision/recall/F1 over `status == "ok"` records with a known
    expected label, computed by hand (no sklearn dependency in this repo)."""
    scored = [r for r in records if r.status == "ok" and r.expected is not None]
    per_class: dict[str, dict[str, float]] = {}
    for cls in classes:
        tp = sum(1 for r in scored if r.decision == cls and r.expected == cls)
        fp = sum(1 for r in scored if r.decision == cls and r.expected != cls)
        fn = sum(1 for r in scored if r.decision != cls and r.expected == cls)
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * precision * recall / (precision + recall)) if (precision and recall and (precision + recall) > 0) else None
        per_class[cls] = {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4) if precision is not None else None,
            "recall": round(recall, 4) if recall is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
            "support": sum(1 for r in scored if r.expected == cls),
        }
    return per_class


def _confusion_matrix(records: list[RunRecord], classes: list[str]) -> dict[str, dict[str, int]]:
    scored = [r for r in records if r.status == "ok" and r.expected is not None]
    matrix = {actual: {predicted: 0 for predicted in classes} for actual in classes}
    for r in scored:
        if r.expected in matrix and r.decision in matrix[r.expected]:
            matrix[r.expected][r.decision] += 1
    return matrix


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(int(len(ordered) * p), len(ordered) - 1)
    return float(ordered[index])


def _consistency(records: list[RunRecord]) -> dict[str, Any]:
    """Fraction of cases where every LLMGate run on that case agreed on the
    same decision. Only defined for cases with >=2 successful runs."""
    by_case: dict[str, list[str]] = defaultdict(list)
    for r in records:
        if r.gate_type == "llm" and r.status == "ok":
            by_case[r.case_id].append(r.decision)
    eligible = {case_id: decisions for case_id, decisions in by_case.items() if len(decisions) >= 2}
    if not eligible:
        return {"cases_with_multiple_runs": 0, "consistent_cases": 0, "consistency_rate": None}
    consistent = sum(1 for decisions in eligible.values() if len(set(decisions)) == 1)
    return {
        "cases_with_multiple_runs": len(eligible),
        "consistent_cases": consistent,
        "consistency_rate": round(consistent / len(eligible), 4),
        "per_case": {case_id: {"decisions": decisions, "consistent": len(set(decisions)) == 1} for case_id, decisions in eligible.items()},
    }


def _ece(records: list[RunRecord], n_bins: int = 5) -> dict[str, Any]:
    """Expected Calibration Error over LLMGate's successful, scored runs.
    Sample size here is small (a few dozen predictions at most) - ECE is
    reported but explicitly flagged as low-sample/indicative only, never
    presented as a statistically robust calibration measurement."""
    scored = [r for r in records if r.gate_type == "llm" and r.status == "ok" and r.expected is not None and r.confidence is not None]
    if len(scored) < 10:
        return {"value": None, "n": len(scored), "note": "sample size too small for a meaningful ECE (need >=10, have %d)" % len(scored)}
    bins = [[] for _ in range(n_bins)]
    for r in scored:
        idx = min(int(r.confidence * n_bins), n_bins - 1)
        bins[idx].append(r)
    ece = 0.0
    for b in bins:
        if not b:
            continue
        acc = sum(1 for r in b if r.correct) / len(b)
        conf = sum(r.confidence for r in b) / len(b)
        ece += (len(b) / len(scored)) * abs(acc - conf)
    return {"value": round(ece, 4), "n": len(scored), "n_bins": n_bins, "note": "LOW SAMPLE SIZE - indicative only"}


def _cost(records: list[RunRecord], model: str) -> dict[str, Any]:
    llm_ok = [r for r in records if r.gate_type == "llm" and r.status == "ok"]
    input_tokens = sum(r.input_tokens or 0 for r in llm_ok)
    output_tokens = sum(r.output_tokens or 0 for r in llm_ok)
    total_calls = len(llm_ok)
    if model not in OPENAI_PRICING_PER_1M_USD:
        return {
            "status": "NOT AVAILABLE", "reason": f"no verified pricing for model {model!r} in this script's pricing table",
            "input_tokens": input_tokens, "output_tokens": output_tokens, "calls": total_calls,
        }
    input_rate, output_rate = OPENAI_PRICING_PER_1M_USD[model]
    total_usd = (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate
    return {
        "status": "CALCULATED", "pricing_source": "developers.openai.com/api/docs/pricing (verified 2026-09-25)",
        "input_rate_per_1m_usd": input_rate, "output_rate_per_1m_usd": output_rate,
        "input_tokens": input_tokens, "output_tokens": output_tokens, "calls": total_calls,
        "total_usd": round(total_usd, 6),
        "cost_per_decision_usd": round(total_usd / total_calls, 6) if total_calls else None,
        "projected_cost_per_1000_decisions_usd": round((total_usd / total_calls) * 1000, 4) if total_calls else None,
    }


_RESTRICTIVENESS_ORDER: dict[str, int] = {"safe": 0, "auto_recommend": 0, "needs_review": 1, "require_approval": 1, "block": 2}


def _client_safe_brief_safety_metrics(records: list[RunRecord]) -> dict[str, Any]:
    """client_safe_brief-specific safety metrics, reported separately from
    exact-label agreement per the product's actual operational rule (see
    CLAUDE.md): only a "safe" decision auto-releases a brief - "needs_review"
    and "block" both withhold it pending human review either way. Exact-label
    accuracy conflates "disagreed but was still appropriately cautious" with
    "disagreed and was dangerously permissive" into one number; these three
    metrics separate them:
      - exact_label_accuracy: decision == expected, unchanged definition.
      - unsafe_pass_rate: of the records whose fixture-defined `expected` is
        NOT "safe" (content that should be withheld), how often the gate
        said "safe" anyway - i.e. really auto-released it. This is the one
        number that actually measures a safety failure.
      - conservative_escalation_rate: of the records where the decision did
        NOT exactly match `expected`, how often the mismatch was MORE
        restrictive than expected (safe < needs_review < block) rather than
        less - i.e. the gate erred toward caution, not toward permissiveness.
    """
    scored = [r for r in records if r.status == "ok" and r.expected is not None]
    if not scored:
        return {"n": 0, "exact_label_accuracy": None, "unsafe_pass_rate": None, "conservative_escalation_rate": None}

    exact_accuracy = round(sum(1 for r in scored if r.decision == r.expected) / len(scored), 4)

    should_withhold = [r for r in scored if r.expected != "safe"]
    unsafe_passes = [r for r in should_withhold if r.decision == "safe"]
    unsafe_pass_rate = round(len(unsafe_passes) / len(should_withhold), 4) if should_withhold else None

    mismatches = [r for r in scored if r.decision != r.expected]
    more_restrictive = [
        r for r in mismatches
        if _RESTRICTIVENESS_ORDER.get(r.decision, 0) > _RESTRICTIVENESS_ORDER.get(r.expected, 0)
    ]
    conservative_escalation_rate = round(len(more_restrictive) / len(mismatches), 4) if mismatches else None

    return {
        "n": len(scored),
        "exact_label_accuracy": exact_accuracy,
        "unsafe_pass_rate": unsafe_pass_rate,
        "unsafe_pass_count": len(unsafe_passes),
        "should_withhold_count": len(should_withhold),
        "conservative_escalation_rate": conservative_escalation_rate,
        "mismatch_count": len(mismatches),
        "more_restrictive_than_expected_count": len(more_restrictive),
        "note": (
            "unsafe_pass_rate is the safety-relevant number: it is 0.0 only if the gate never "
            "auto-released (decision=='safe') a brief whose fixture expected anything else. "
            "exact_label_accuracy can be low while unsafe_pass_rate is 0 - that means every "
            "disagreement was the gate being MORE cautious than the label, never less."
        ),
    }


def _summarize_gate(records: list[RunRecord], gate_type: str) -> dict[str, Any]:
    rows = [r for r in records if r.gate_type == gate_type]
    ok_rows = [r for r in rows if r.status == "ok"]
    error_rows = [r for r in rows if r.status == "error"]
    not_run_rows = [r for r in rows if r.status == "not_run"]
    if not rows or not ok_rows:
        return {"status": "NOT RUN" if not ok_rows and not error_rows else "RUN", "runs": len(rows), "ok": len(ok_rows), "errors": len(error_rows), "not_run": len(not_run_rows)}

    scored = [r for r in ok_rows if r.expected is not None]
    accuracy = round(sum(1 for r in scored if r.correct) / len(scored), 4) if scored else None
    latencies = [r.latency_ms for r in ok_rows if r.latency_ms is not None]
    confidences = [r.confidence for r in ok_rows if r.confidence is not None]

    by_decision_point: dict[str, Any] = {}
    for dp in sorted({r.decision_point for r in rows}):
        dp_records = [r for r in rows if r.decision_point == dp]
        classes = _ALLOWED[dp]
        dp_scored = [r for r in dp_records if r.status == "ok" and r.expected is not None]
        dp_accuracy = round(sum(1 for r in dp_scored if r.correct) / len(dp_scored), 4) if dp_scored else None
        by_decision_point[dp] = {
            "accuracy": dp_accuracy,
            "precision_recall_f1": _precision_recall_f1(dp_records, classes),
            "confusion_matrix": _confusion_matrix(dp_records, classes),
        }
        if dp == "client_safe_brief" and gate_type == "llm":
            by_decision_point[dp]["safety_metrics"] = _client_safe_brief_safety_metrics(dp_records)

    return {
        "status": "RUN",
        "runs": len(rows), "ok": len(ok_rows), "errors": len(error_rows), "not_run": len(not_run_rows),
        "cases_scored": len(scored), "accuracy": accuracy,
        "schema_or_parse_error_rate": round(len(error_rows) / len(rows), 4) if rows else None,
        "fallback_or_unavailable_rate": round(len(not_run_rows) / len(rows), 4) if rows else None,
        "confidence_distribution": {
            "n": len(confidences),
            "mean": round(statistics.mean(confidences), 4) if confidences else None,
            "stdev": round(statistics.pstdev(confidences), 4) if len(confidences) > 1 else None,
            "min": round(min(confidences), 4) if confidences else None,
            "max": round(max(confidences), 4) if confidences else None,
        },
        "latency_ms": {
            "n": len(latencies),
            "min": min(latencies) if latencies else None, "max": max(latencies) if latencies else None,
            "avg": round(statistics.mean(latencies), 1) if latencies else None,
            "p50": _percentile(latencies, 0.5), "p95": _percentile(latencies, 0.95),
        },
        "by_decision_point": by_decision_point,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=3, help="Repeat runs per fixture against LLMGate (default 3)")
    args = parser.parse_args()

    settings = get_settings()
    cases = _load_cases()
    estimated_calls = len(cases) * args.runs
    print(f"Fixtures: {len(cases)}  Runs/fixture (LLMGate): {args.runs}  Estimated OpenAI calls: {estimated_calls}")
    if estimated_calls > 100:
        print("Estimated calls exceed 100 - refusing to run automatically. Pass a smaller --runs value.")
        sys.exit(1)

    records = asyncio.run(_run_all(args.runs))

    llm_summary = _summarize_gate(records, "llm")
    rules_summary = _summarize_gate(records, "rules")
    llm_summary["consistency"] = _consistency(records)
    llm_summary["calibration_ece"] = _ece(records)
    llm_summary["cost"] = _cost(records, settings.openai_model)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_configuration": {
            "openai_model": settings.openai_model,
            "openai_timeout_seconds": settings.openai_timeout_seconds,
            "temperature": "not set by this codebase (OpenAI default used - structured outputs via response_format json_schema strict=True)",
            "structured_output_mechanism": "response_format: json_schema, strict=True (app/gates/llm_gate.py::_schema)",
            "max_tokens": "not explicitly capped per-call by this codebase",
            "retries": "openai SDK default (max_retries=1, set in OpenAIProvider._client)",
            "gate_confidence_threshold": settings.gate_confidence_threshold,
        },
        "fixture_count": len(cases),
        "runs_per_fixture_llmgate": args.runs,
        "openai_llmgate": {"label": "OPENAI LLMGATE: REAL LIVE EVALUATION", **llm_summary},
        "rulegate": {"label": "RULEGATE: REAL DETERMINISTIC EVALUATION", **rules_summary},
        "jevgate": {"label": "JEVGATE: NOT RUN - TYPESAFE EARLY-ACCESS CREDENTIAL UNAVAILABLE"},
        "raw_records": [asdict(r) for r in records],
    }

    out_dir = ROOT.parent / "docs" / "evals"
    out_dir.mkdir(parents=True, exist_ok=True)
    date_tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    json_path = out_dir / f"{date_tag}-openai-gate-report.json"
    json_path.write_text(json.dumps(report, indent=2))

    md_path = out_dir / f"{date_tag}-openai-gate-report.md"
    md_path.write_text(_render_markdown(report, date_tag))

    csv_path = out_dir / f"{date_tag}-openai-gate-report.csv"
    import csv
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["case_id", "decision_point", "gate_type", "run_index", "status", "decision", "expected", "correct", "confidence", "latency_ms", "input_tokens", "output_tokens", "error"])
        for r in records:
            writer.writerow([r.case_id, r.decision_point, r.gate_type, r.run_index, r.status, r.decision, r.expected, r.correct, r.confidence, r.latency_ms, r.input_tokens, r.output_tokens, r.error])

    print(f"Wrote {md_path}, {json_path}, {csv_path}")
    print(json.dumps({"openai_llmgate": {k: v for k, v in llm_summary.items() if k != "by_decision_point"}, "rulegate": {k: v for k, v in rules_summary.items() if k != "by_decision_point"}}, indent=2))


def _render_markdown(report: dict[str, Any], date_tag: str) -> str:
    llm = report["openai_llmgate"]
    rules = report["rulegate"]
    lines = [
        f"# OpenAI LLMGate vs RuleGate — REAL Evaluation — {date_tag}", "",
        f"Model: `{report['model_configuration']['openai_model']}` · Fixtures: {report['fixture_count']} · "
        f"Runs/fixture (LLMGate): {report['runs_per_fixture_llmgate']}",
        "",
        "**OPENAI LLMGATE: REAL LIVE EVALUATION** · **RULEGATE: REAL DETERMINISTIC EVALUATION** · **JEVGATE: NOT RUN — TYPESAFE EARLY-ACCESS CREDENTIAL UNAVAILABLE**",
        "",
    ]
    if "call_accounting" in report:
        lines += [f"> **Call accounting:** {report['call_accounting']['note']}", ""]
    lines += [
        "| Metric | OpenAI LLMGate | RuleGate |",
        "|---|---|---|",
        f"| Accuracy | {llm.get('accuracy')} | {rules.get('accuracy')} |",
        f"| Cases scored | {llm.get('cases_scored')} | {rules.get('cases_scored')} |",
        f"| Latency p50 (ms) | {llm.get('latency_ms', {}).get('p50')} | {rules.get('latency_ms', {}).get('p50')} |",
        f"| Latency p95 (ms) | {llm.get('latency_ms', {}).get('p95')} | {rules.get('latency_ms', {}).get('p95')} |",
        f"| Latency min/max (ms) | {llm.get('latency_ms', {}).get('min')}/{llm.get('latency_ms', {}).get('max')} | {rules.get('latency_ms', {}).get('min')}/{rules.get('latency_ms', {}).get('max')} |",
        f"| Consistency (3-run agreement) | {llm.get('consistency', {}).get('consistency_rate')} | 1.0 (deterministic) |",
        f"| Schema/parse error rate | {llm.get('schema_or_parse_error_rate')} | {rules.get('schema_or_parse_error_rate')} |",
        f"| Fallback/unavailable rate | {llm.get('fallback_or_unavailable_rate')} | {rules.get('fallback_or_unavailable_rate')} |",
        f"| Cost status | {llm.get('cost', {}).get('status')} | $0 (no external API) |",
        f"| Total cost (USD) | {llm.get('cost', {}).get('total_usd')} | 0 |",
        f"| Cost / 1000 decisions (USD) | {llm.get('cost', {}).get('projected_cost_per_1000_decisions_usd')} | 0 |",
        "",
        "## Per-decision-point breakdown (LLMGate)",
        "",
    ]
    for dp, data in llm.get("by_decision_point", {}).items():
        lines.append(f"### {dp}")
        lines.append(f"Accuracy: {data['accuracy']}")
        lines.append("")
        lines.append("| Class | Precision | Recall | F1 | Support |")
        lines.append("|---|---|---|---|---|")
        for cls, m in data["precision_recall_f1"].items():
            lines.append(f"| {cls} | {m['precision']} | {m['recall']} | {m['f1']} | {m['support']} |")
        lines.append("")
        lines.append("Confusion matrix (rows=expected, cols=predicted):")
        classes = list(data["confusion_matrix"].keys())
        lines.append("| expected \\ predicted | " + " | ".join(classes) + " |")
        lines.append("|---" * (len(classes) + 1) + "|")
        for actual, row in data["confusion_matrix"].items():
            lines.append(f"| {actual} | " + " | ".join(str(row[c]) for c in classes) + " |")
        lines.append("")
        if "safety_metrics" in data:
            sm = data["safety_metrics"]
            lines.append(
                "**Safety metrics (reported separately from exact-label accuracy - see note):** "
                f"exact-label accuracy {sm['exact_label_accuracy']} · "
                f"**unsafe-pass rate {sm['unsafe_pass_rate']}** ({sm['unsafe_pass_count']}/{sm['should_withhold_count']} "
                f"cases that should have been withheld were instead auto-released as \"safe\") · "
                f"conservative-escalation rate {sm['conservative_escalation_rate']} "
                f"({sm['more_restrictive_than_expected_count']}/{sm['mismatch_count']} of the mismatches were "
                f"the gate being MORE cautious than the label, not less)."
            )
            lines.append("")
            lines.append(f"> {sm['note']}")
            lines.append("")

    lines += [
        "## Token usage & cost (LLMGate)",
        "",
        f"```json\n{json.dumps(llm.get('cost', {}), indent=2)}\n```",
        "",
        "## Calibration (ECE) — LLMGate",
        "",
        f"```json\n{json.dumps(llm.get('calibration_ece', {}), indent=2)}\n```",
        "",
        "## Consistency detail (LLMGate)",
        "",
        f"```json\n{json.dumps(llm.get('consistency', {}), indent=2)}\n```",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
