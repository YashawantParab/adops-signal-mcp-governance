# SignalOps AI — Guidance for Claude Code Sessions

## Architecture

- `backend/` — FastAPI + SQLAlchemy + Alembic, Postgres in prod (Neon/Render), SQLite locally.
- `frontend/` — Next.js app, `app/mcp-governance/*` is the governance UI (dashboard, agent console, run detail, approvals, tool registry).
- `mcp-server/` — standalone FastMCP server (`adops_signal_mcp`). Imports `backend/app/*` for DB access via `bootstrap.py` sys.path insertion. Runs as a subprocess of the backend, not embedded in-process.
- `data/`, `docs/policies/` — seed fixtures and governance policy markdown read by `search_policy_context`.

## Two agent paths — do not conflate them

1. **`POST /api/mcp/agent/run` — Phase 1 primary path.** A governed LLM agent
   (`backend/app/agent/mcp_agent_runtime.py`) that dynamically picks MCP tools,
   calls them through `governance_wrapper.governed_tool_call` (registry →
   permission → scope → audit-log → real MCP call → result logging), and
   produces an evidence-grounded diagnosis. `execution_mode` on the response
   and DB row is either `llm_mcp_agent` (primary) or `deterministic_fallback`
   (rule-based, no LLM/MCP), with an explicit `fallback_reason` whenever it
   fell back. **MCP calls are real stdio protocol calls to the standalone
   `mcp-server/` subprocess** — never direct Python function calls dressed up
   as MCP.
2. **`POST /api/agent/diagnose` — legacy path, untouched by Phase 1.** Uses
   `AdOpsSignalAgent` (`backend/app/agent/signal.py` + `llm_reasoner.py`) with
   its own RAG/grounded-fallback logic and its own `execution_mode` values
   (`llm_rag` / `fallback`). It does **not** use MCP. Do not describe it as
   MCP-based, and do not port Phase 1 governance concepts into it without a
   deliberate decision — they are intentionally separate systems.

## Governance invariants (never relax these silently)

- A tool result must pass registry validation → permission check (read-only
  only) → scope check (tool's `campaign_id` must match the investigation's
  scoped campaign) → audit row write, **before** it ever reaches the LLM.
- The agent loop is bounded: `MAX_AGENT_STEPS`, `MAX_AGENT_TOOL_CALLS`,
  `MAX_AGENT_TOKENS`, `AGENT_TIMEOUT_SECONDS`. Provider SDK calls run via
  `loop.run_in_executor` specifically so the timeout can actually preempt a
  hung call — don't move that call back inline without re-verifying timeout
  behavior.
- A final diagnosis's root causes may only cite `evidence_id`s that were
  actually produced by a real tool call in that same run. Fabricated/
  cross-run/nonexistent evidence IDs must be rejected, not trimmed-and-kept.
- HIGH risk → approval request (execution blocked pending human decision).
  CRITICAL risk → blocked action. Neither path ever executes a campaign,
  budget, or pacing change — this whole subsystem only recommends and gates.

## Public `/demo` — zero-write invariant

`demo_viewer` must never be able to create `agent_runs`, `mcp_tool_calls`,
`approval_requests`, `policy_checks`, `blocked_actions`, `gate_decisions`,
`proposed_actions`, `action_executions`, `mcp_access_tokens`, or
`run_feedback`. It is rejected at
the FastAPI role dependency (403), not inside the handler. Any new mutating
governance endpoint must exclude `DEMO_VIEWER_ROLE` from `require_roles(...)`
and get a regression test proving zero writes
(`backend/tests/test_public_demo_mode.py`).

## Decision gates (Phase 2 — System 1 on top of the System 2 agent)

`backend/app/gates/` implements a provider-neutral `DecisionGate` (`base.py`):
`RuleGate` (deterministic, always available), `LLMGate` (reuses the same
`LLMProvider.classify()` the agent's own provider exposes), `JevGate`
(TypeSafe AI Jev — **early access; `typesafe-sdk==0.7.1` IS a pinned
`requirements.txt` dependency and the adapter is fully implemented against
its real contract, but `TYPESAFE_API_KEY` is not available (waitlist full) so
it has never been exercised live**; reports itself unavailable until a key is
set — see `docs/jev-integration-notes.md` and
`docs/JEV_ACTIVATION_RUNBOOK.md`). `DECISION_GATE_PROVIDER` selects the
primary gate; unavailable gates fall back `jev -> llm -> rules`, and RuleGate
is the unconditional backstop (`app/gates/__init__.py::get_decision_gate_chain`).

Three gate points are wired into `_run_llm_mcp_agent_orchestration`
(`mcp_governance_service.py`) — **only for `execution_mode="llm_mcp_agent"`
runs, never the deterministic fallback**:

- **`risk_routing`** — may only *escalate* the deterministic rule floor
  (LOW/MEDIUM→`auto_recommend`, HIGH→`require_approval`, CRITICAL→`block`),
  never downgrade it (`app/gates/base.py::apply_rule_floor`, unconditionally
  enforced, not gate-specific). A gate decision below
  `GATE_CONFIDENCE_THRESHOLD` is treated as at least `require_approval`.
- **`evidence_verification`** — supplements, never replaces, the
  deterministic evidence-ID existence/scope check in
  `mcp_agent_runtime.py::_grounded_causes`. `unsupported` removes a cause
  outright; `uncertain` is persisted for audit but not removed (a coarse
  gate's uncertainty isn't grounds to discard an already evidence-ID-verified
  cause).
- **`client_safe_brief`** — the finish call now also produces
  `GovernedDiagnosis.client_safe_brief`; anything but `safe` is withheld
  (`agent_runs.client_safe_brief` stays `NULL`, only `client_safe_brief_status`
  is set) rather than auto-released or silently rewritten.

Every gate call persists a `gate_decisions` row (`gate_decision_service.py`).
`tool_scope`, `prompt_injection_screen`, and `risk_queue_triage` decision
points exist and are tested (`app/gates/decision_points.py`) but are **not
wired into the live agent loop** — a deliberate Phase 2 scope cut (they were
explicitly secondary/"if it fits cleanly"); don't assume they run just
because the code exists.

Adversarial gate fixtures: `backend/evals/adversarial_cases.json` +
`tests/test_adversarial_gate_fixtures.py` (deterministic, CI-safe). The live,
multi-gate comparison (`python -m evals.gate_evaluation`) is manual-only —
never runs in CI, never fabricates a number for an unconfigured gate (reports
`NOT RUN`).

## Closed action loop (Phase 3 — synthetic only)

`backend/app/services/mock_ad_server.py` + `action_execution_service.py`
implement `propose -> pending_approval -> approved -> executed -> verified`,
with human-authorized rollback, against **synthetic** campaign settings on the
existing `campaigns` table (`frequency_cap`, `target_devices`, `status`) — no
real ad server anywhere. Four narrow action types:
`adjust_frequency_cap`, `relax_device_constraint`, `pause_campaign`,
`resume_campaign`. Hard rules enforced in `action_execution_service.py`, not
just documented:
- `execute_action` refuses anything not `status == "approved"`.
- `risk_class == "CRITICAL"` never reaches `approved` (blocked at proposal —
  reuses the same `_score_risk`/rule-floor logic as Phase 2's risk-routing
  gate) and is re-checked at execution as defense in depth.
- Approval reuses the existing `approval_requests` table (one unified queue)
  — a `reviewer_id` must be a real human, set only via the role-gated
  `/api/actions/{id}/approve` endpoint; there is no code path for the agent
  itself to call it.
- `state_version` (a hash of pre-approval campaign state) is checked again at
  execution time; a materially changed campaign since approval fails with
  `STALE_APPROVAL` rather than executing against stale assumptions.
- Every execution is immediately verified (re-read state vs. requested state)
  and every rollback restores and re-verifies — both are their own persisted
  rows (`action_verifications`, `action_rollbacks`), not just implied by
  success.
- `/api/actions/*` excludes `DEMO_VIEWER_ROLE` on every write, same as every
  other governance write surface.

## Hosted external MCP (Phase 3F/G)

`backend/app/hosted_mcp.py` mounts the SAME FastMCP instance the stdio path
uses (`mcp-server/adops_signal_mcp/server.py`) at `POST /mcp/external`,
in-process (not a subprocess) via `FastMCP.streamable_http_app()`. Two things
about this that are easy to get wrong if touched again:
- The session manager's lifespan (`fastmcp_instance.session_manager.run()`)
  is entered/exited manually across `app.main`'s own `@app.on_event`
  startup/shutdown hooks — `app.mount()` does **not** propagate a mounted
  sub-app's own lifespan automatically, so skipping this makes every request
  hang or fail once the session manager needs to actually run.
- `fastmcp_instance.settings.streamable_http_path` is forced to `"/"` before
  calling `streamable_http_app()`, otherwise the inner app's own default
  route (`/mcp`) composes with the mount prefix into a doubled path.

Auth/rate-limit/audit (`ExternalMCPAuthMiddleware`) runs before any request
reaches the MCP session manager: bearer token verified against
`mcp_access_tokens` (only a SHA-256 hash is ever stored — the raw token is
returned once, at creation, via `POST /api/mcp-tokens`, admin/adops_manager
only), per-token rate limit via the existing `app/rate_limit.py`, and every
request logged to `external_mcp_calls`. This surface is read-only by
construction (the mounted FastMCP instance declares no write tools) — it has
no path to `/api/actions`, `/api/mcp/approvals`, or any other write endpoint.
Verified against a real running Docker container in this session (real
`initialize` → `notifications/initialized` → `tools/call` → real campaign
data, real 401/429 responses, real `external_mcp_calls` audit rows in
Postgres) — see the Phase 3 final report for the transcript.

Two new MCP resources (`campaign://{campaign_id}/summary`,
`policy://{filename}`) and one prompt (`investigate_campaign_delivery`) exist
on both the stdio and hosted paths — see `docs/mcp-tool-registry.md`.

## Feedback (Phase 3H)

`POST /api/mcp/runs/{run_id}/feedback` (thumbs up/down + optional comment,
`run_feedback` table) — excludes `DEMO_VIEWER_ROLE` like every other write.
Shown in the Governance Record run-detail page.

## Schema changes

Alembic only (`backend/alembic/versions/`) — never mutate schema ad hoc.
Local/dev boot also runs `Base.metadata.create_all()` on startup (pre-existing
behavior), but production schema changes must still go through a migration.

## Observability — never fabricate

`execution_mode`, `llm_provider`, `model_name`, token counts, `steps_used`,
`max_steps`, `fallback_reason` are persisted only when actually known.
`estimated_cost_usd` is `None` unless a provider SDK genuinely returns a
dollar cost — do not compute or guess one. Eval metrics
(`evals/run_evaluation.py`) must reflect an actual run; never state a pass/
fail or a score without having executed it in this session.

## Key commands

```bash
# Backend tests (from backend/)
pytest -q
python -m evals.run_evaluation
python -m evals.gate_evaluation  # manual only - real network calls if OPENAI_API_KEY/TYPESAFE_API_KEY set

# Alembic
alembic upgrade head
alembic downgrade -1

# Frontend (from frontend/)
npm run typecheck
npm run build

# Docker (from repo root)
docker compose config
docker compose build
docker compose up -d
```

## Do not, without explicit instruction

- Auto-deploy, reseed Neon, or otherwise touch production/staging data.
- Commit or push on the user's behalf.
- Claim a test passed, a live LLM call happened, or real MCP protocol was
  used without having actually run it in this session.
