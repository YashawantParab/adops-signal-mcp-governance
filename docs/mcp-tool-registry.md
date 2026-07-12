# MCP Tool Registry

This repository exposes MCP-shaped tools through **two** surfaces that intentionally call the same underlying backend service functions rather than duplicating logic. This document is the registry for both. For how these tools compose into a governed run, see [Architecture → Approval Workflow](./architecture.md#approval-workflow). For local install/run instructions, see [MCP Local Setup](./mcp-local-setup.md).

| Surface | Where | Protocol | Writes governance data? |
|---|---|---|---|
| Standalone MCP server | `mcp-server/adops_signal_mcp/server.py` | Real MCP (`FastMCP`), stdio or Streamable HTTP | No — pure read tools |
| Embedded governance API | `backend/app/api/mcp.py`, `backend/app/services/mcp_governance_service.py` | REST (`/api/mcp/*`) | Yes — `agent_runs`, `mcp_tool_calls`, `approval_requests`, `policy_checks`, `blocked_actions` |

Neither surface can mutate a campaign, budget, bid, targeting, or creative record. There is no MCP tool, in either surface, that executes the proposed action it evaluates — every proposed action stays a recommendation until a human decides.

## Standalone MCP Server — Tools

Seven tools, all read-only, all returning `{"ok": true, ...}` or a typed `{"ok": false, "error": {code, message, details?}}` payload. Long arrays are shortened below for readability — see [MCP Local Setup](./mcp-local-setup.md) for full example payloads.

### `ping_adops_signal()`

- **Input:** none
- **Output:** MCP server readiness, database connectivity, environment
- **Risk:** Low / System

### `get_campaign_health(campaign_id: int)`

- **Input schema:** `{campaign_id: integer, minimum 1}`
- **Output:** pacing percentage, expected/actual delivery, risk level, creative status, VAST error count, inventory summary, bid analysis, main suspected issue
- **Errors:** `INVALID_CAMPAIGN_ID`, `CAMPAIGN_NOT_FOUND`, `CAMPAIGN_HEALTH_FAILED`
- **Risk:** Low / Campaign Signals

### `get_campaign_pacing(campaign_id: int)`

- **Output:** latest pacing snapshot, prior-snapshot trend (direction + delta), remaining-delivery forecast (flight days remaining, required daily impressions), full history
- **Errors:** `INVALID_CAMPAIGN_ID`, `CAMPAIGN_NOT_FOUND`, `PACING_DATA_NOT_FOUND`, `CAMPAIGN_PACING_FAILED`
- **Risk:** Low / Campaign Signals

### `get_vast_validation_summary(campaign_id: int)`

- **Output:** creative approval status counts, rejected count, VAST error count, error-code counts, severity counts, rejection reasons, up to 10 latest errors, suggested fix
- **Errors:** `INVALID_CAMPAIGN_ID`, `CAMPAIGN_NOT_FOUND`, `CREATIVE_DATA_NOT_FOUND`, `VAST_VALIDATION_SUMMARY_FAILED`
- **Risk:** Low / Creative Governance

### `get_brand_safety_findings(campaign_id: int)`

- **Output:** deterministic findings list (`type`, `severity`, `message`, `evidence`), read from sensitive content categories, regulated advertiser vertical, rejected creatives, VAST error volume, and any recommendation text that references brand safety
- **Errors:** `INVALID_CAMPAIGN_ID`, `CAMPAIGN_NOT_FOUND`, `NO_BRAND_SAFETY_FINDINGS`, `BRAND_SAFETY_FINDINGS_FAILED`
- **Risk:** Medium / Brand Safety — the only standalone-server tool marked above Low, because its output directly feeds escalation decisions downstream

### `get_recommendation_history(campaign_id: int)`

- **Output:** recommendation count, status counts, full recommendation list with reviewer name/role and decision rationale. Read-only — does not approve, reject, or modify anything.
- **Errors:** `INVALID_CAMPAIGN_ID`, `CAMPAIGN_NOT_FOUND`, `RECOMMENDATION_HISTORY_NOT_FOUND`, `RECOMMENDATION_HISTORY_FAILED`
- **Risk:** Low / Governance History

### `search_policy_context(query: str)`

- **Input schema:** `{query: string, 1–200 chars}`
- **Output:** ranked matches from `docs/policies/*.md` — source path, title, score, matched keywords, snippet — plus a `retrieval` block stating `method: "keyword"`, `vector_db_used: false`, `llm_used: false`
- **Errors:** `INVALID_POLICY_QUERY`, `POLICY_CONTEXT_UNAVAILABLE`, `POLICY_CONTEXT_NOT_FOUND`, `POLICY_CONTEXT_SEARCH_FAILED`
- **Risk:** Low / Policy — explicitly not a vector/LLM system; keyword scoring only, by design, for auditability

## Embedded Governance API — Tool Descriptors

`GET /api/mcp/tools` serves the same six data-reading tools above (minus `ping_adops_signal`, which has no REST equivalent) as structured descriptors, annotated with `category`, `permission_level`, `risk_level`, and — because this surface persists every call — live `call_count`, `failure_rate`, and `last_used_at` computed from `mcp_tool_calls`. This is the registry the `/mcp-governance/tools` frontend page renders.

| Tool | Category | Permission | Risk level |
|---|---|---|---|
| `ping_adops_signal` | System | read | Low |
| `get_campaign_health` | Campaign Signals | read | Low |
| `get_campaign_pacing` | Campaign Signals | read | Low |
| `get_vast_validation_summary` | Creative Governance | read | Low |
| `get_brand_safety_findings` | Brand Safety | read | Medium |
| `get_recommendation_history` | Governance History | read | Low |
| `search_policy_context` | Policy | read | Low |

`risk_level` here describes the sensitivity of the tool's *output*, not the risk of the campaign it's called against — that scoring happens separately in the [risk engine](./architecture.md#risk-model).

## Governed Orchestration: `POST /api/mcp/agent/run`

This is not itself an MCP tool — it is the deterministic orchestration endpoint that calls five of the tools above in sequence, in this fixed order, logging each as an `mcp_tool_calls` row:

1. `get_campaign_health`
2. `get_campaign_pacing`
3. `get_vast_validation_summary`
4. `get_brand_safety_findings`
5. `search_policy_context` (queried with `f"{user_query} {main_suspected_issue}"`)

It then scores risk, derives a proposed action from any pending recommendation (or a generic root-cause statement), writes a `policy_checks` row, and — depending on the risk band — writes an `approval_requests` or `blocked_actions` row. Full request/response examples and curl commands are in [MCP Governance Backend API](./mcp-governance-api.md).

## Resources and Prompts

Neither MCP surface currently declares MCP **resources** (addressable, subscribable data, e.g. `campaign://1045/health`) or MCP **prompts** (reusable prompt templates served through the protocol). Both are natural next steps discussed in [Product Case Study → Future Roadmap](./product-case-study.md#future-roadmap):

- A `campaign://` resource scheme would let an MCP client browse campaign state directly, rather than only calling tools.
- A `diagnose-underdelivery` prompt template would package the exact investigative sequence `run_agent_orchestration` runs today into a reusable MCP prompt, so any MCP client — not just this product's own UI — could trigger the same governed investigation.

Today, every capability is exposed as a tool call, which is sufficient for the current scope but is explicitly called out here rather than left as a silent gap.

## Adding a New Tool

Any new tool must, at minimum:

1. Be read-only, or clearly gated behind the same approval-request/blocked-action pattern if it can propose a state change.
2. Return the `{"ok": bool, ...}` / typed-error contract used by every existing tool.
3. Be added to `MCP_TOOL_DESCRIPTORS` in `backend/app/services/mcp_governance_service.py` so it appears in the registry and its calls are tracked.
4. Reuse an existing backend service function rather than querying the database directly, so the standalone MCP server and the embedded governance API cannot silently diverge in behavior.
