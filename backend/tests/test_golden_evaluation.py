from evals.run_evaluation import evaluate


def test_golden_diagnostic_suite_meets_quality_floor():
    report = evaluate()
    assert report["cases"] == 17  # 15 original + G16/G17 (campaigns 1050, 1051)
    assert report["root_cause_recall"] >= 0.90
    assert report["evidence_grounding_rate"] == 1.0
    assert report["client_safe_guardrail_pass_rate"] == 1.0
    assert report["governance_workflow_passed"] is True
