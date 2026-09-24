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
`approval_requests`, `policy_checks`, or `blocked_actions`. It is rejected at
the FastAPI role dependency (403), not inside the handler. Any new mutating
governance endpoint must exclude `DEMO_VIEWER_ROLE` from `require_roles(...)`
and get a regression test proving zero writes
(`backend/tests/test_public_demo_mode.py`).

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
