from evals.run_evaluation import evaluate


def test_golden_diagnostic_suite_meets_quality_floor():
    report = evaluate()
    assert report["cases"] == 15
    assert report["root_cause_recall"] >= 0.90
    assert report["evidence_grounding_rate"] == 1.0
