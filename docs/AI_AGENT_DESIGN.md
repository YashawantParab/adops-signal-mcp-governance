# AI Agent Design

## Product Decision

AdOps Signal uses an LLM for diagnosis and recommendation reasoning, but it does not give the model unrestricted database access. Bounded tools collect campaign evidence first; RAG retrieves operating guidance; the model returns a strict schema; a validator rejects unsupported citations.

The orchestrator first classifies the operator question into a focused investigation lens: comprehensive, targeting/inventory, creative/VAST, bid competitiveness, frequency cap, launch timing, shared inventory pressure, goal feasibility, client communication, or next action. Each lens has its own bounded tool plan. This prevents a targeting question from returning an unrelated full-campaign answer and gives the LLM a smaller, more relevant evidence context.

This separates three concerns:

- **Facts:** SQL-backed tools owned by the product.
- **Reasoning:** LLM synthesis and prioritization.
- **Control:** deterministic validation, RBAC, audit, and human approval.

## Why An Agent

A dashboard can show metrics, but campaign troubleshooting requires selecting evidence across pacing, setup, supply, creative delivery, and auctions, then forming and testing competing explanations. An agent is justified when it reduces this cross-system reasoning and preserves the evidence path.

The agent is not justified for simple metric lookup. Those questions should continue to use direct APIs and dashboards.

## Workflow

1. Validate authenticated user and campaign context.
2. Call pacing, campaign setup, targeting, inventory, portfolio pressure, VAST, and bid tools.
3. Assign immutable evidence IDs.
4. Retrieve relevant playbook chunks through vector similarity.
5. Send only necessary campaign context, evidence, and guidance to the model.
6. Require structured JSON matching `GroundedDiagnosis`.
7. Remove root causes that cite unknown evidence IDs.
8. Persist pending recommendations and the full audit trace.
9. Return model name, prompt version, execution mode, latency, confidence, and sources.
10. Fall back to grounded deterministic diagnosis if the provider is absent or fails.

## Model Strategy

- Default reasoning model: `gpt-5.4-mini`, selected for a lower-latency, lower-cost operational workflow.
- Model is configurable and should be pinned to a tested snapshot for production.
- Embeddings: `text-embedding-3-small` when configured; local 1536-dimensional hashing supports offline development.
- The application remains provider-isolated behind `LLMReasoner`.

The model receives no credentials, raw database connection, or ability to execute campaign changes.

## Prompt Contract

The system prompt requires:

- Only evidence-backed claims.
- Exact evidence-ID citations.
- Impact-based ranking.
- No claim that a recommendation was executed.
- Human approval for targeting, bids, frequency, inventory, flight, or creative changes.
- Separation of campaign evidence from retrieved general guidance.

The output is validated through Pydantic before it reaches a user.

## RAG

Operational Markdown playbooks are:

1. Split into sections.
2. Embedded into 1536-dimensional vectors.
3. Stored in `knowledge_chunks`.
4. Retrieved by cosine similarity.
5. Passed to the model as guidance, never as campaign-specific proof.

PostgreSQL uses pgvector distance operations. SQLite loads vectors for local cosine comparison.

## Confidence

Model confidence is capped at 0.95 and displayed as a decision aid, not a probability of correctness. Production calibration requires historical incidents and expert agreement. Confidence must never override missing evidence.

## Human Control

- Recommendations start in `pending`.
- AdOps Manager and Admin roles can approve or reject.
- Every decision requires a rationale and stores reviewer identity and timestamp.
- The prototype records decisions but does not mutate live campaigns.
- Client-safe summaries exclude publisher floors, raw loss reasons, internal tool names, and validation traces.

## Failure Modes

| Failure | Detection | Product behavior |
|---|---|---|
| LLM unavailable | Provider exception or missing key | Marked fallback response |
| Unsupported citation | Unknown evidence ID | Cause removed; fallback if none remain |
| Stale pacing | Snapshot timestamp/absence | Lower-confidence evidence; future freshness alert |
| Missing inventory mapping | No eligible segment data | Explicit insufficient-data state |
| Conflicting causes | Similar evidence strength | Return ranked multi-causality |
| Prompt injection in docs | Retrieved content separated as untrusted guidance | Model instruction hierarchy and output validator |
| Approval bypass | Role mismatch | HTTP 403 and audit event |

## Evaluation

The release gate includes:

- 15 golden diagnostic scenarios.
- 90% minimum root-cause recall.
- 100% evidence-ID coverage.
- Zero unsupported high-impact recommendations.
- Provider-specific latency and token reporting when a key is configured.

See [EVALUATION_REPORT.md](./EVALUATION_REPORT.md).

## Compute And Cost

The online path is dominated by one reasoning call and optional embeddings. Structured campaign evidence is compact enough to avoid long-context processing. Prompt caching, model-tier routing, and asynchronous proactive diagnoses are future cost controls. Self-hosted open-weight models would only be considered if data residency, volume, or unit economics justify GPU operational complexity.
