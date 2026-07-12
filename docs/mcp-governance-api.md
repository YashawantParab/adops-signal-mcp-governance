# MCP Governance Backend API

The backend persists MCP governance records in the existing application database. The MCP server remains read-only and separate; these API routes expose stored runs, tool calls, policy checks, blocked actions, and approval request decisions.

## Migrate

From the repository root:

```bash
cd backend
../backend/.venv/bin/python -m alembic upgrade head
```

## Seed

```bash
cd backend
../backend/.venv/bin/python seed.py
```

The seed includes:

- 8 `agent_runs`
- 26 `mcp_tool_calls`
- 5 `approval_requests`
- 4 `policy_checks`
- 3 `blocked_actions`

## Run The API

```bash
cd backend
../backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

## Authenticate

```bash
curl -s -X POST http://127.0.0.1:8001/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"adops@demo.adops.local","password":"SignalDemo!2026"}'
```

Use the returned `access_token`:

```bash
export TOKEN="paste-token-here"
```

## API Checks

```bash
curl -s http://127.0.0.1:8001/api/mcp/runs \
  -H "Authorization: Bearer $TOKEN"
```

```bash
curl -s http://127.0.0.1:8001/api/mcp/runs/9001 \
  -H "Authorization: Bearer $TOKEN"
```

```bash
curl -s http://127.0.0.1:8001/api/mcp/approvals \
  -H "Authorization: Bearer $TOKEN"
```

```bash
curl -s -X POST http://127.0.0.1:8001/api/mcp/approvals/9201/approve \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"rationale":"Evidence reviewed; approve controlled inventory expansion planning only."}'
```

```bash
curl -s -X POST http://127.0.0.1:8001/api/mcp/approvals/9203/reject \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"rationale":"Reject until brand-suitability review is complete."}'
```

```bash
curl -s http://127.0.0.1:8001/api/mcp/tools \
  -H "Authorization: Bearer $TOKEN"
```

## Agent Orchestration Run

`POST /api/mcp/agent/run` composes the same read-only signals already exposed as MCP tools (campaign health, pacing, VAST validation, brand safety, policy search) into one deterministic, auditable run. It never mutates campaign, budget, or pacing data - it only ever writes governance/audit rows (`agent_runs`, `mcp_tool_calls`, `approval_requests`, `blocked_actions`, `policy_checks`).

Workflow: create an agent run, read campaign health/pacing/VAST/brand-safety, search policy context, score the proposed action's risk (LOW/MEDIUM/HIGH/CRITICAL), open an approval request on HIGH risk, open a blocked action on CRITICAL risk (e.g. a rejected creative that must not serve), log every tool call, then complete the run with a final recommendation.

```bash
curl -s -X POST http://127.0.0.1:8001/api/mcp/agent/run \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"user_query":"Why is RheinAuto behind pacing and what should we do?","campaign_id":"1045"}'
```

Seed data reference points for exercising each risk band:

- `campaign_id: "1045"` (RheinAuto CTV Launch) -> `HIGH`, creates an `approval_request`.
- `campaign_id: "1046"` (NordicStream Family Addressable) -> `CRITICAL`, has a rejected creative, creates a `blocked_action`.
- `campaign_id: "1047"` (LuxeHome Premium Video) -> `LOW`, no escalation.

```bash
curl -s -X POST http://127.0.0.1:8001/api/mcp/agent/run \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"user_query":"Can the rejected NordicStream creative serve?","campaign_id":"1046"}'
```

An unparseable `campaign_id` returns `422`; an unknown campaign returns `404`. Both are rejected before an agent run is created, since `agent_runs.campaign_id` is a required foreign key.

```bash
curl -s http://127.0.0.1:8001/api/mcp/summary \
  -H "Authorization: Bearer $TOKEN"
```

Approval and rejection endpoints update only `approval_requests`. They do not mutate campaign budget, pacing, targeting, creative serving, or recommendation records.

