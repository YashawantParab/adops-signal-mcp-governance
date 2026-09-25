from evals.run_evaluation import evaluate


def test_golden_diagnostic_suite_meets_quality_floor():
    report = evaluate()
    assert report["cases"] == 17  # 15 original + G16/G17 (campaigns 1050, 1051)
    # root_cause_recall is category-based (evals/root_cause_categories.py) - a
    # deterministic, auditable taxonomy, not exact-string match - see
    # run_evaluation.py's module-level note for why exact match is not a fair
    # test of live LLM output. root_cause_recall_exact_match is reported
    # alongside for transparency but never gates this test.
    assert report["root_cause_recall"] >= 0.90
    assert report["cases_with_uncategorized_causes"] == []
    assert report["evidence_grounding_rate"] == 1.0
    assert report["client_safe_guardrail_pass_rate"] == 1.0
    assert report["governance_workflow_passed"] is True
