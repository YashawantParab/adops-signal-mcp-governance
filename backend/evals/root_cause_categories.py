"""Deterministic root-cause category taxonomy for the golden evaluation suite.

Why this exists: evals/golden_cases.json's `expected_all` labels ("Narrow
targeting", "VAST validation issue", ...) are exact strings the deterministic
fallback engine (app/agent/signal.py) happens to produce verbatim - confirmed
by running the golden suite with no LLM key configured, which scores 17/17
(1.0) recall under pure exact-string matching. Exact-string matching is only
a fair comparison against THAT deterministic path. A real, live LLM diagnoses
the same underlying condition but writes its own sentence, e.g. "Eligible
inventory is highly constrained by the current device and content-category
targeting" - the same *category* of finding ("narrow targeting") as the
fallback's fixed string, in different words. Comparing that free text against
a fixed string with `==` will always fail regardless of how correct the live
diagnosis is - it was never a fair evaluation method for a live model.

The golden fixture's full label set is a small, closed vocabulary (8 distinct
labels across 17 cases, enumerated by inspecting golden_cases.json directly),
so a genuine "deterministic normalized semantic label" scheme - the top tier
of the preferred hierarchy - is actually available here without any model
judge: map both the golden label and the model's free-text cause to one of a
fixed set of category keys via keyword matching, and compare category-to-
category. This function is intentionally conservative (substring/keyword
matching only, no fuzzy logic, no embeddings) so every categorization is
auditable by reading this file - it does not attempt semantic understanding
beyond what these keyword patterns literally capture, and that limit is
reported explicitly by the evaluation harness (see UNCATEGORIZED handling in
run_evaluation.py), not hidden.
"""
from __future__ import annotations

UNCATEGORIZED = "uncategorized"

# Ordered most-specific-first: a text is tested against each category in this
# order and assigned to the first one whose keywords match. Order matters
# where categories share vocabulary (e.g. both narrow_targeting and
# device_targeting_mismatch can mention "device" and "targeting").
#
# Coverage note: seed.py's ad-request `failure_reason` codes are the source
# of several dynamically-titled deterministic causes (app/agent/signal.py
# does `top_failure_reason.replace("_", " ").title()`). The complete set of
# codes, read directly from seed.py, is: targeting_mismatch,
# frequency_cap_exceeded, device_targeting_mismatch, publisher_category_block,
# shared_inventory_consumed_by_high_priority_campaign, bid_below_floor,
# auction_lost, publisher_allocation_below_forecast,
# weekend_inventory_concentration - every one of them has an explicit keyword
# entry below so none can silently fall through to UNCATEGORIZED.
_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "targeting_mismatch",
        (
            "device targeting mismatch", "targeting mismatch", "targeting_mismatch", "device mismatch",
            "device-level mismatch", "wrong device type", "device exclusion",
        ),
    ),
    (
        "narrow_targeting",
        (
            "narrow targeting", "eligible inventory", "eligible supply", "eligible daily impressions",
            "is eligible", "targeting is too", "targeting is very restrictive", "too narrow for",
            "narrow for the current", "restrictive targeting", "device and content-category",
            "device and content category", "targeting constraint", "constrained by the current device",
            "severely constraining supply", "modeled supply", "modeled inventory",
        ),
    ),
    (
        "vast_validation_issue",
        (
            "vast validation", "vast error", "vast issue", "vast/creative", "creative/vast",
            "tracking uri", "tracking request", "media file", "companion ad", "creative validation error",
        ),
    ),
    (
        "creative_rejected",
        ("creative rejected", "creative was rejected", "creative disapprov", "rejected creative", "creative approval"),
    ),
    (
        "publisher_category_block",
        ("publisher category block", "category block", "blocked by publisher", "publisher content category"),
    ),
    (
        "bid_below_floor",
        (
            "bid price below floor", "bid below floor", "bid competitiveness", "not competitive enough",
            "noncompetitive", "non-competitive", "below floor", "below publisher floor", "win rate",
            "auction lost", "auction", "bid levels", "floor", "bid-win",
        ),
    ),
    (
        "frequency_cap",
        ("frequency cap", "repeat reach"),
    ),
    (
        "campaign_started_late",
        (
            "started late", "start was delayed", "launch delay", "delayed start", "late launch",
            "launch was delayed", "days after campaign start", "days after the scheduled", "delayed onset",
            "did not begin until", "after campaign start", "after the scheduled campaign start", "after launch",
        ),
    ),
    (
        "shared_inventory_pressure",
        (
            "shared inventory", "inventory pressure", "portfolio pressure", "other campaigns",
            "consuming inventory", "high-priority campaign", "high-priority inventory", "displaced by shared",
        ),
    ),
    (
        "publisher_supply_shortfall",
        ("allocation below forecast", "publisher allocation", "supply shortfall", "under-allocated"),
    ),
    (
        "inventory_timing_pattern",
        ("weekend inventory concentration", "inventory concentration", "day-of-week", "weekend concentration"),
    ),
    (
        "goal_attainment_risk",
        ("goal attainment", "hit its goal", "hit the goal", "attain the goal", "goal feasib"),
    ),
    (
        "campaign_behind_pacing",
        ("behind pacing", "behind plan", "behind pace", "pacing is"),
    ),
    (
        "no_blocker",
        ("no critical blocker", "no dominant", "no issue found", "no blocker detected"),
    ),
]


def categorize(text: str) -> str:
    """Map free text (a golden label, or a real cause sentence) to its single
    highest-priority matching category, or UNCATEGORIZED if none match. Used
    where a text needs exactly one label (e.g. reporting/debug output). Never
    raises; never guesses beyond literal keyword presence."""
    lowered = text.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return category
    return UNCATEGORIZED


def categorize_multi(text: str) -> set[str]:
    """All matching categories for one text, not just the first. A single
    cause sentence can legitimately describe more than one underlying
    condition at once - e.g. a real observed live cause combined "eligible
    inventory is only 11.9%" (narrow_targeting) and "79.3% of requests failed
    with targeting_mismatch as the dominant reason" (targeting_mismatch) in
    one sentence. Returns {UNCATEGORIZED} only when nothing matches at all."""
    lowered = text.lower()
    matches = {category for category, keywords in _CATEGORY_KEYWORDS if any(keyword in lowered for keyword in keywords)}
    return matches or {UNCATEGORIZED}


def categorize_all(texts: set[str]) -> set[str]:
    """Union of every category matched across a set of texts - the right
    granularity for recall matching (does this set of causes, taken
    together, cover the expected category set), as opposed to forcing each
    individual cause into exactly one bucket."""
    result: set[str] = set()
    for text in texts:
        result |= categorize_multi(text)
    return result
