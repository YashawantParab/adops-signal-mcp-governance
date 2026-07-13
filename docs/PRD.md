# Product Requirements: SignalOps AI — MCP Governance Control Plane for AdOps Agents

> Live demo: [adops-signal-mcp-governance.vercel.app/mcp-governance](https://adops-signal-mcp-governance.vercel.app/mcp-governance) · Stack: Next.js (Vercel) → Next.js API proxy → FastAPI (Render) → Neon Postgres. See [Architecture](./architecture.md) for the full system diagram and [Product Case Study](./product-case-study.md) for the narrative walkthrough.

## 1. Product Overview

SignalOps AI is a governance control plane for AI agents operating on AdOps/CTV campaign data. It is not another dashboard, not a VAST validator, and not autonomous campaign execution. An agent investigates a campaign through a fixed set of bounded, read-only MCP tools; a deterministic risk engine scores whatever action the investigation implies; and depending on that score, the action either clears with no escalation, is routed to a human reviewer, or is blocked outright. Every tool call, risk score, policy check, and human decision is written to a durable audit trail.

The system runs as a deployed product, not a slide deck: a Next.js frontend on Vercel calls a FastAPI backend on Render through a same-origin API proxy; the backend persists all governance state in Neon Postgres. Two MCP-shaped surfaces exist — an embedded governance API (`/api/mcp/*`) that the product UI drives, and a standalone MCP server (`mcp-server/`) exposing the same read-only tools to any MCP client (MCP Inspector, Claude Desktop). All data is synthetic — see [Synthetic Data Disclaimer](#12-synthetic-data-disclaimer).

## 2. Problem Statement

Three converging pressures make agent governance a real, current product problem:

1. **Agents are getting tool access faster than governance is catching up.** MCP standardizes how an agent calls a tool; it says nothing about who should decide when a tool's output implies an action that shouldn't happen automatically.
2. **AdOps decisions carry real cost when wrong.** A wrongly approved budget shift, a creative that shouldn't have served, or a brand-safety miss on a regulated advertiser vertical cost bookings and client trust.
3. **"The agent explained its reasoning" is not the same as "this action was authorized."** Most agent demos stop at explainability. Adopting agents in a regulated, financially exposed workflow requires an accountable decision trail: what was proposed, how risky was it, who approved it, and when.

## 3. Target Users

| User | Decision this system supports |
|---|---|
| AdOps Manager | Which proposed action is safe to approve, and on what evidence? |
| Platform / Trust & Safety Lead | Is agent tool usage across the platform inspectable and rate-bounded by risk? |
| Product Manager | Which recurring risk patterns deserve a platform investment, and is the tool registry healthy? |
| Engineering Lead evaluating MCP | What does a governed MCP tool surface look like in working code, not in theory? |

## 4. Jobs-To-Be-Done

| User | Job to be done | Current cost without this system |
|---|---|---|
| AdOps Manager | Decide whether to approve or reject a risky proposed action, backed by evidence, in one place | Slack-thread approvals with no consistent record or rationale |
| Platform / Trust & Safety Lead | Confirm that every agent tool call is enumerable, bounded to read-only, and rate/risk-visible | No registry; tool usage is opaque and ungoverned |
| Product Manager | See tool reliability, approval volume, and risk mix across the whole agent fleet | Fragmented, per-incident knowledge with no aggregate view |
| Engineering Lead | Evaluate whether a governance pattern (registry, risk score, approval gate, audit log) generalizes to other agents | Bespoke, one-off governance code per agent, none of it reusable |

## 5. Core User Journeys

The primary journey a reviewer or operator walks end to end:

1. **Prioritize.** The MCP Governance dashboard (`/mcp-governance`) surfaces run volume, risk mix, pending approvals, blocked actions, and tool failure rates.
2. **Investigate.** An operator submits a campaign to the Agent Console (`/mcp-governance/agent`). The agent calls a fixed sequence of read-only MCP tools — campaign health, pacing, VAST validation, brand-safety findings, and policy-context search — each logged before any conclusion is reached.
3. **Score.** The deterministic risk engine turns that evidence into a 0–100 score and a band (LOW/MEDIUM/HIGH/CRITICAL) — see [Risk Scoring](#9-risk-scoring).
4. **Route.** LOW/MEDIUM scores return a recommendation with no escalation. HIGH scores open a pending approval request. CRITICAL scores block the action outright and it never reaches a human queue.
5. **Decide.** For HIGH-risk runs, an authorized reviewer approves or rejects the proposed action in the Decision Queue (`/mcp-governance/approvals`) with a required rationale.
6. **Verify.** The Governance Record (`/mcp-governance/runs/[run_id]`) joins the tool-call timeline, risk score, policy check, and human decision into one inspectable trace.

Seed-data reference points that exercise all three outcomes: Campaign 1045 (RheinAuto CTV Launch) → HIGH → approval request; Campaign 1046 (NordicStream Family Addressable, rejected creative) → CRITICAL → blocked action; Campaign 1047 (LuxeHome Premium Video) → LOW → no escalation.

## 6. Functional Requirements

- The MCP tool registry is enumerable: every tool's name, input schema, output contract, category, and risk level is inspectable (`GET /api/mcp/tools`, `/mcp-governance/tools`).
- No MCP tool mutates campaign, budget, bid, targeting, or creative data. All seven tools are strictly read-only.
- `POST /api/mcp/agent/run` composes campaign health, pacing, VAST validation, brand-safety findings, and policy-context search into one governed, audited investigation, and persists every call as an `mcp_tool_calls` row before any conclusion is produced.
- Every run is scored by the deterministic risk engine and assigned exactly one band: LOW, MEDIUM, HIGH, or CRITICAL.
- A HIGH-risk run creates a pending `approval_requests` row; a CRITICAL-risk run creates a `blocked_actions` row and is never queued for approval.
- Only `admin` or `adops_manager` roles can approve or reject a pending request, and every decision requires a written rationale.
- Re-deciding an already-decided approval request returns `409 Conflict` rather than silently overwriting the prior decision.
- Reads of runs, approvals, tool registry, and summary counts are available to `admin`, `adops_manager`, `product_manager`, and the read-only public demo role.
- A full run (query, tool calls, risk score, policy check, human decision) is reconstructable after the fact via `GET /api/mcp/runs/{id}` and its corresponding UI page.
- `search_policy_context` retrieves against the governance policy corpus in `docs/policies/` and reports its own retrieval mode (`vector_db_used`, `llm_used`) rather than implying capability it doesn't have.

## 7. Non-Functional Requirements

- **Reliability:** health (`/health`) and readiness (`/ready`, includes DB connectivity) endpoints; the frontend detects and surfaces Render free-tier cold starts (up to ~60s) instead of showing a broken page.
- **Security:** JWT access tokens with issuer/audience/role/expiration; salted PBKDF2-SHA256 password storage; role-gated mutations; CORS allowlist; security headers; production disables interactive API docs.
- **Auditability:** governance writes (`agent_runs`, `mcp_tool_calls`, `policy_checks`, `approval_requests`, `blocked_actions`) are append-only from the run's perspective — approval decisions update in place, but the originating run and its tool calls are immutable.
- **Explainability:** every run reports which tools were called, their inputs/outputs, the resulting risk score and band, and the policy check outcome — not just a final recommendation sentence.
- **Observability:** structured JSON logs, request IDs, Prometheus metrics (`/metrics`) including tool call latency and status.
- **Portability:** Docker Compose for local development; deployed independently on Vercel (frontend), Render (backend), and Neon (database).
- **Determinism:** the risk engine is a fixed, reproducible rule function — identical inputs always produce identical scores — so demo and pilot behavior is repeatable and inspectable, not a second opaque model call.

## 8. MCP Tool Governance

Two MCP-shaped surfaces expose the same underlying backend service functions, so behavior cannot silently diverge between them:

- **Embedded governance API** (`backend/app/api/mcp.py`) — the product-facing surface driving `/mcp-governance/*`. `POST /api/mcp/agent/run` composes tool calls into one governed, audited investigation and writes governance rows.
- **Standalone MCP server** (`mcp-server/`, built on `FastMCP`) — a real Model Context Protocol server reachable over stdio or Streamable HTTP from any MCP client (MCP Inspector, Claude Desktop). It exposes the same seven read-only tools individually but does not run the risk engine or write governance rows. See [MCP Local Setup](./mcp-local-setup.md).

Registry (see [MCP Tool Registry](./mcp-tool-registry.md) for full schemas):

| Tool | Reads | Mutates |
|---|---|---|
| `ping_adops_signal` | Server + database readiness | No |
| `get_campaign_health` | Pacing %, risk level, creative status, VAST error count, bid analysis | No |
| `get_campaign_pacing` | Latest + historical pacing snapshots, delivery trend | No |
| `get_vast_validation_summary` | Creative approval state, persisted VAST errors by code/severity | No |
| `get_brand_safety_findings` | Deterministic brand-safety findings from targeting, vertical, creative status | No |
| `get_recommendation_history` | Prior recommendations and reviewer decisions for a campaign | No |
| `search_policy_context` | Keyword search over `docs/policies/*.md` | No |

Governance requirement: no tool in this registry executes or mutates the action it evaluates. Any future write-capable tool (see [Future Roadmap](#14-future-roadmap)) must go through the same registry/risk/approval/audit pattern, not a bypass.

## 9. Risk Scoring

A deterministic, additive 0–100 scoring function (`backend/app/services/mcp_governance_service.py::_score_risk`), not a model judgment call:

```text
score  = pacing_risk_weight[health.risk_level]      # High=45, Medium=25, Low=8, Unknown=15
       + 25 if any creative is rejected
       + min(vast_error_count * 3, 15)
       + sum(finding_severity_weight[f] for f in brand_safety_findings)
                                                       # high=15, medium=8, low=3
```

| Score | Band | Outcome |
|---|---|---|
| ≥ 85, or (rejected creative AND a high-severity finding) | CRITICAL | Action blocked; `blocked_actions` row written; never queued for approval |
| ≥ 60 | HIGH | `approval_requests` row written; pending human decision |
| ≥ 35 | MEDIUM | `policy_checks.result = "review_required"`; no escalation row |
| < 35 | LOW | `policy_checks.result = "clear"`; no escalation row |

Weights are informed by, and `search_policy_context` retrieves against, the governance policy corpus in [`docs/policies/`](./policies/) (brand safety, budget shift, human approval, VAST validation). Choosing a rule engine over an LLM-scored risk assessment is deliberate: the layer deciding whether a human needs to see something must be reproducible on its own terms, not another opaque inference call sitting on top of the first one.

## 10. Human Approval Workflow

- A HIGH-risk run opens a pending `approval_requests` row containing the proposed action, risk score, risk level, and a generated rationale.
- Only `admin` or `adops_manager` roles can call `POST /api/mcp/approvals/{id}/approve` or `/reject`.
- Every approval/rejection decision requires a written rationale — there is no one-click approve with no reason recorded.
- Approving or rejecting an already-decided request returns `409 Conflict` rather than silently overwriting the prior decision.
- Reviewers work the queue at `/mcp-governance/approvals`.
- CRITICAL-risk actions bypass this queue entirely: they are written to `blocked_actions` and never reach a human decision point, because some outcomes (e.g. a rejected creative serving) should not be one reviewer's call to casually override.

See [Architecture → Approval Workflow](./architecture.md#approval-workflow) for the full sequence diagram.

## 11. Audit Trail / Governance Record

Every step of a governed run writes durable rows, not just UI state:

| Table | Role |
|---|---|
| `agent_runs` | One row per governed investigation: query, campaign, status, risk score/level, final recommendation |
| `mcp_tool_calls` | One row per tool invocation: tool name, input/output JSON, latency, status |
| `policy_checks` | Policy documents matched during the run and the resulting governance outcome |
| `approval_requests` | HIGH-risk proposed actions pending human decision: proposed action, risk score, rationale, reviewer, decision timestamp |
| `blocked_actions` | CRITICAL-risk actions that were never queued for approval |

A complete run is reconstructable after the fact via `GET /api/mcp/runs/{id}` and the `/mcp-governance/runs/[run_id]` page: what was asked, what evidence was read, what the risk score was, what governance outcome followed, who reviewed it, and when. Nothing is deleted; approval decisions update `approval_requests` in place, but the originating run and its tool calls are immutable history.

## 12. Synthetic Data Disclaimer

Every campaign, advertiser, publisher, creative, VAST error, pacing snapshot, and policy document is a synthetic fixture generated by `backend/seed.py` (`RANDOM_SEED = 1045`) for demonstration purposes. Nothing in this repository connects to a real ad server, SSP, DSP, or production customer data. This is a portfolio-grade working prototype: no claim is made of real production deployment, real customer usage, or validated customer adoption. See [Known Limitations](../README.md#known-limitations) and [Product Case Study → Limitations](./product-case-study.md#limitations).

## 13. Out Of Scope

- Direct mutation of live campaign settings, budget, bid, targeting, or creative serving — no tool in the registry can write.
- Autonomous action execution — the agent proposes; a human or the risk engine's block decides.
- Contractual makegood decisions.
- Production customer data or a connected pilot against a real ad server, SSP, or DSP.
- Enterprise SSO/OIDC (demo authentication only, in this iteration).
- A hosted, authenticated endpoint for the standalone MCP server (it is a local-only milestone today).
- MCP resources and MCP prompts (only MCP tools are exposed today).
- Semantic/vector retrieval for policy search (current `search_policy_context` is keyword-based and reports this honestly in its own output).

## 14. Future Roadmap

- **MCP resources.** A `campaign://{id}/health` resource scheme so an MCP client can browse campaign state directly rather than only calling tools.
- **MCP prompts.** Package the fixed investigative tool sequence as a reusable MCP prompt template so any MCP client can trigger the same governed investigation.
- **Hosted, authenticated MCP endpoint.** Move the standalone server from a local stdio/HTTP milestone to an authenticated, rate-limited deployment reachable by external MCP clients.
- **Real policy retrieval.** Replace keyword search with semantic retrieval over a reviewed, expanded governance policy corpus.
- **Write-path governance.** Extend the same registry/risk/approval/audit pattern to a tightly scoped write tool (e.g. pausing a campaign), as the real test of whether this governance model holds up once actions have direct consequences.
- **Connected pilot.** Read-only integration with a real ad server or SSP, so risk scoring and approval routing can be validated against real incident data instead of seeded fixtures.

---

Related documents: [Product Case Study](./product-case-study.md) (narrative walkthrough) · [Architecture](./architecture.md) (system diagram, APIs, database, deployment) · [MCP Tool Registry](./mcp-tool-registry.md) (full tool schemas) · [MCP Governance Backend API](./mcp-governance-api.md) (migration, seed, curl examples) · [Product Strategy](./PRODUCT_STRATEGY.md) (wedge, buyer, monetization, roadmap).
