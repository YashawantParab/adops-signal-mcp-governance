# AI Agent Design

## Product Decision

SignalOps AI uses an LLM for diagnosis and recommendation reasoning, but it does not give the model unrestricted database access. Bounded tools collect campaign evidence first; RAG retrieves operating guidance; the model returns a strict schema; a validator rejects unsupported citations.

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
2. Call the campaign summary, pacing, campaign setup, targeting, inventory, portfolio pressure, VAST, and bid tools.
3. Assign immutable evidence IDs.
4. Retrieve relevant playbook chunks through vector similarity.
5. Send only necessary campaign context, evidence, and guidance to the model.
6. Require structured JSON matching `GroundedDiagnosis`.
7. Remove root causes that cite unknown evidence IDs.
8. Persist pending recommendations and the full audit trace.
9. Return campaign ID, root causes, evidence, confidence, risk level, recommended actions, tool
   calls used, playbook sources used, model name, prompt version, execution mode, and latency.
10. Fall back to grounded deterministic diagnosis if the provider is absent or fails.

Recommendation creation and client-safe brief generation are deliberately *not* folded into this
same bounded-tool call list. They are downstream, human-relevant artifacts gated by approval and
audit, not automated evidence-gathering steps — collapsing them into the tool trace would blur the
separation of Facts / Reasoning / Control this design is built around. Both consume the same
evidence (the client-safe brief also retrieves playbook guidance; see RAG below) and both are
visible as distinct stages in the UI and in `docs/DEMO_SCRIPT.md`.

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

Operational Markdown playbooks (`data/adops_docs/*.md`: pacing, VAST/creative, inventory
targeting, client-safe communication, governance/approval policy) are:

1. Split into sections.
2. Embedded into 1536-dimensional vectors.
3. Stored in `knowledge_chunks`.
4. Retrieved by cosine similarity.
5. Passed to the model — and returned to the API/UI as structured `playbook_sources`
   (source file, title, snippet, similarity score) — as guidance, never as campaign-specific proof.

Retrieval is used both when diagnosing and when generating the client-safe brief, so client
communication is grounded in the same playbook guidance as the diagnosis, not just raw metrics.

Every retrieved chunk honestly reports which backend produced it, rather than implying pgvector
when it isn't the active path:

- **Search backend:** `pgvector_cosine_distance` on PostgreSQL (used by Docker Compose and
  production), or `in_memory_cosine_fallback` on SQLite (used only by the local unit test suite).
- **Embedding provider:** `local-hash-1536` (deterministic, offline, the default) or
  `text-embedding-3-small` when `RAG_EMBEDDING_PROVIDER=openai` and a key is configured.

The local-hash embedding is a real 1536-dimensional vector derived from token hashing, indexed and
queried through the same pgvector cosine-distance path as OpenAI embeddings — the vector math and
the database column are genuine. What it does **not** provide is production-grade semantic
relevance: for short operator questions it is a noisy signal (confirmed empirically — see
`EVALUATION_REPORT.md`), so treat its retrieval *quality* as a development placeholder even though
the retrieval *mechanism* is real.

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
| Client-safe brief leaks internal terms | Golden-suite guardrail check scans generated briefs for forbidden terms | Release gate fails if any leakage is found |

## Evaluation

The release gate includes:

- 15 golden diagnostic scenarios.
- 90% minimum root-cause recall.
- 100% evidence-ID coverage.
- Zero unsupported high-impact recommendations.
- 100% client-safe brief guardrail pass rate (no internal-term leakage).
- A passing diagnose → approve → audit governance round trip.
- Provider-specific latency and token reporting when a key is configured.

See [EVALUATION_REPORT.md](./EVALUATION_REPORT.md).

## Tool Registry & MCP Readiness

The agent's tool surface is ten bounded functions in `app/agent/tools.py`, called by exactly one
orchestrator (`AdOpsSignalAgent`). We evaluated adding a full [Model Context
Protocol](https://modelcontextprotocol.io) server and deliberately did not build one: MCP earns its
complexity when multiple agent hosts, or an external partner, need to invoke the same tools over a
standard transport. Neither condition holds here, and running a second process just to demonstrate
the acronym would add real failure surface (auth over MCP, another container, another thing that
can break the demo recording) for zero visible workflow improvement — the opposite of this
project's own principle of not adding infrastructure just because it sounds impressive.

Instead, `app/agent/tool_registry.py` declares every tool as a `ToolDescriptor` — `name`,
`description`, `input_schema`, `output_contract` — in the same shape an MCP tool listing would use,
served read-only at `GET /api/agent/tools`. This is a descriptor registry, not a protocol
implementation: it makes the bounded-tool design enumerable and inspectable today without adding a
server, a transport, or a new consumer that doesn't yet exist.

**The condition that would flip this decision:** a second agent host (e.g. a separate internal
tool, or an external partner's agent) needing to call these same evidence tools. At that point, a
thin MCP server wrapping the existing `app/agent/tools.py` functions behind this registry's
metadata would be a same-day addition, not a redesign.

## Compute And Cost

The online path is dominated by one reasoning call and optional embeddings. Structured campaign evidence is compact enough to avoid long-context processing. Prompt caching, model-tier routing, and asynchronous proactive diagnoses are future cost controls. Self-hosted open-weight models would only be considered if data residency, volume, or unit economics justify GPU operational complexity.
