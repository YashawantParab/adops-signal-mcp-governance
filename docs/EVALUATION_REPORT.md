# Evaluation Report

## Executive Summary

AdOps Signal is evaluated against 15 deterministic campaign troubleshooting cases spanning pacing, narrow targeting, creative rejection, VAST errors, bid floors, frequency caps, delayed launch, device mismatch, and shared inventory pressure.

| Metric | Current result | Release floor |
|---|---:|---:|
| Golden cases | 15 | 15 |
| Grounded fallback root-cause recall | 100% | 90% |
| Evidence provenance coverage | 100% | 100% |
| Backend tests | 13 passing | 100% passing |
| Query-intent differentiation | 3/3 focused lenses | 3/3 |
| Unsupported root-cause tolerance | 0 | 0 |

The measured 100% result applies to the deterministic synthetic evaluation set and grounded fallback. It is not a claim of production accuracy on real CTV platform incidents.

## Evaluation Design

Each golden case contains:

- A campaign and natural-language operator question.
- One or more expected root-cause labels.
- Optional evidence terms that must be present.
- A requirement that every returned root cause cites valid evidence IDs.

The suite is stored in `backend/evals/golden_cases.json`. Run it with:

```bash
cd backend
python -m evals.run_evaluation
```

## Coverage

| Scenario | Campaign | Golden cases |
|---|---:|---:|
| Narrow country/device/category targeting | 1045, 1047, 1048 | G01, G02, G09, G10 |
| Creative rejection / missing companion | 1046 | G04, G05 |
| VAST timeout or media validation | 1045, 1048 | G03, G13 |
| Frequency cap pressure | 1046 | G04, G06 |
| Below-floor bids | 1047, 1049 | G07, G08, G14 |
| Device targeting mismatch | 1048 | G10, G11 |
| Late campaign start | 1048 | G12 |
| Shared high-priority inventory pressure | 1049 | G15 |

## LLM Evaluation Status

The repository supports structured OpenAI reasoning when `OPENAI_API_KEY` is configured. A live-model benchmark is intentionally not reported because no API key was available during this build. The same golden runner automatically records `execution_mode=llm_rag` when a key is present.

Before a customer pilot:

1. Run the suite against the pinned production model three times.
2. Report mean root-cause recall, evidence precision, invalid citation rate, latency, and token cost.
3. Add at least 50 anonymized incidents labeled independently by two AdOps experts.
4. Calibrate confidence against expert agreement instead of trusting model self-confidence.
5. Block rollout if unsupported-claim rate is above zero for high-impact actions.

## Known Biases

- The seed data was created to express known failure scenarios.
- Ground-truth labels are authored from those same scenarios.
- Real incidents contain missing data, delayed signals, and ambiguous multi-causality.
- The current suite tests diagnosis quality, not whether recommended changes improve live delivery.
