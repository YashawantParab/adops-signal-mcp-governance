# MCP Local Setup

This repository exposes the first MCP governance milestone as a separate Python server under `mcp-server/`.
It reuses the existing SignalOps AI backend models, database configuration, and campaign health service.

For the product framing of why this exists, see the [product case study](./product-case-study.md); for the same tools' schemas and the governed-orchestration API that composes them, see the [MCP tool registry](./mcp-tool-registry.md) and [architecture](./architecture.md#backend-apis). For a scripted walkthrough of the governed flow this server's tools feed, see the [demo script](./demo-script.md).

All data returned by these tools is seeded and synthetic (`backend/seed.py`) — see the [dataset disclaimer](./architecture.md#dataset-disclaimer). This server is a local-only milestone: it runs manually via stdio or Streamable HTTP, and there is no hosted, authenticated MCP endpoint for external clients yet.

## Requirements

- Python 3.10 or newer for the official MCP Python SDK. Use Python 3.12 or 3.13 locally.
- Do not use the macOS system Python 3.9 runtime for this MCP server.
- The existing backend database. For local development, the default is `backend/adops_signal.db`.
- Optional: Node.js if you want to run MCP Inspector with `npx`.

## Install Dependencies

From the repository root:

```bash
python3.13 -m venv mcp-server/.venv
source mcp-server/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r mcp-server/requirements.txt
```

`python3.12 -m venv mcp-server/.venv` is also fine when Python 3.13 is not installed.

The MCP server honors `DATABASE_URL` when it is set. If `DATABASE_URL` is not set, it uses:

```bash
sqlite:////absolute/path/to/this/repo/backend/adops_signal.db
```

The MCP dependency set is intentionally separate from `backend/requirements.txt`. Current stable MCP SDK releases require
`pydantic>=2.11`, while the existing backend application pins an older pydantic version. Keeping a separate MCP environment
avoids changing the verified backend runtime.

## Run The MCP Server

The default transport is stdio, which is the normal mode for local MCP clients:

```bash
source mcp-server/.venv/bin/activate
PYTHONPATH=mcp-server python -m adops_signal_mcp.server
```

For Streamable HTTP during local inspection:

```bash
source mcp-server/.venv/bin/activate
MCP_TRANSPORT=streamable-http PYTHONPATH=mcp-server python -m adops_signal_mcp.server
```

By default, FastMCP serves Streamable HTTP at:

```text
http://localhost:8000/mcp
```

## Test With MCP Inspector

Start the server in Streamable HTTP mode:

```bash
source mcp-server/.venv/bin/activate
MCP_TRANSPORT=streamable-http PYTHONPATH=mcp-server python -m adops_signal_mcp.server
```

In a second terminal:

```bash
npx -y @modelcontextprotocol/inspector
```

Connect the Inspector to:

```text
http://localhost:8000/mcp
```

Then call:

- `ping_adops_signal` with no arguments.
- `get_campaign_health` with:

```json
{"campaign_id": 1045}
```
- `get_campaign_pacing` with:

```json
{"campaign_id": 1045}
```

- `get_vast_validation_summary` with:

```json
{"campaign_id": 1046}
```

- `get_brand_safety_findings` with:

```json
{"campaign_id": 1045}
```

- `get_recommendation_history` with:

```json
{"campaign_id": 1046}
```

- `search_policy_context` with:

```json
{"query": "budget shift human approval"}
```

## Simple Local Tool Test

This bypasses the MCP transport and calls the tool implementations directly:

```bash
source mcp-server/.venv/bin/activate
PYTHONPATH=mcp-server python -m pytest mcp-server/tests -q
PYTHONPATH=mcp-server python mcp-server/local_tool_test.py
```

Expected successful tool responses are structured JSON with:

```json
{
  "ok": true
}
```

Validation and lookup failures return structured JSON with:

```json
{
  "ok": false,
  "error": {
    "code": "INVALID_CAMPAIGN_ID",
    "message": "campaign_id must be a positive integer."
  }
}
```

## Exposed Tools

Long arrays in the examples below are shortened for readability.

### `ping_adops_signal()`

Returns MCP server readiness and database connectivity.

### `get_campaign_health(campaign_id)`

Validates `campaign_id`, loads the campaign through the existing backend database access layer, and returns the existing campaign health contract:

- pacing percentage
- expected and actual delivery
- risk level
- creative status
- VAST error count
- inventory summary
- bid analysis
- main suspected issue

### `get_campaign_pacing(campaign_id)`

Returns latest and historical pacing snapshots from `pacing_snapshots`.

Example input:

```json
{"campaign_id": 1045}
```

Example output:

```json
{
  "ok": true,
  "campaign_id": 1045,
  "campaign_name": "RheinAuto CTV Launch",
  "latest": {
    "snapshot_date": "2026-06-23",
    "expected_delivery": 777778,
    "actual_delivery": 451111,
    "pacing_percentage": 58.0,
    "risk_level": "High"
  },
  "trend": {
    "previous_pacing_percentage": 61.0,
    "delta_percentage_points": -3.0,
    "direction": "declining"
  },
  "remaining_delivery": {
    "goal_impressions": 1000000,
    "remaining_impressions": 548889,
    "flight_days_remaining": 4,
    "required_daily_impressions": 137222
  },
  "history": []
}
```

### `get_vast_validation_summary(campaign_id)`

Returns creative approval status, persisted VAST errors, error-code counts, severity counts, rejection reasons, and suggested review steps.

Example input:

```json
{"campaign_id": 1046}
```

Example output:

```json
{
  "ok": true,
  "campaign_id": 1046,
  "valid": false,
  "creative_count": 4,
  "approval_status_counts": {
    "approved": 3,
    "rejected": 1
  },
  "rejected_count": 1,
  "vast_error_count": 8,
  "error_code_counts": {
    "COMPANION_MISSING": 4,
    "VAST_TIMEOUT": 4
  },
  "rejection_reasons": [
    "Missing companion asset for addressable TV placement."
  ],
  "latest_errors": [],
  "suggested_fix": "Request a revised creative package with the missing companion asset and resubmit for approval."
}
```

### `get_brand_safety_findings(campaign_id)`

Returns deterministic brand-safety findings from campaign targeting, advertiser vertical, creative status, VAST errors, and recommendation text.

Example input:

```json
{"campaign_id": 1045}
```

Example output:

```json
{
  "ok": true,
  "campaign_id": 1045,
  "campaign_name": "RheinAuto CTV Launch",
  "findings": [
    {
      "type": "creative_quality_governance",
      "severity": "medium",
      "message": "Persisted VAST errors should be reviewed before scaling delivery.",
      "evidence": {
        "vast_error_count": 5
      }
    },
    {
      "type": "recommendation_policy_reference",
      "severity": "low",
      "message": "Existing recommendation explicitly references brand-safety or brand-suitability controls.",
      "evidence": {
        "recommendation_id": 1,
        "title": "Expand eligible CTV inventory",
        "status": "pending"
      }
    }
  ],
  "read_only": true
}
```

### `get_recommendation_history(campaign_id)`

Returns recommendation status history and reviewer metadata. It does not approve, reject, or modify recommendations.

Example input:

```json
{"campaign_id": 1046}
```

Example output:

```json
{
  "ok": true,
  "campaign_id": 1046,
  "campaign_name": "NordicStream Family Addressable",
  "recommendation_count": 1,
  "status_counts": {
    "approved": 1
  },
  "recommendations": [
    {
      "id": 2,
      "title": "Replace rejected creative",
      "status": "approved",
      "decision_reason": "Corrected VAST tag received from the creative agency and revalidated; approved to resume full delivery on the addressable flight.",
      "decided_by_name": "Daniel Keller",
      "decided_by_role": "adops_manager"
    }
  ],
  "read_only": true
}
```

### `search_policy_context(query)`

Searches local markdown files in `docs/policies/` with simple keyword retrieval. It does not use a vector database or LLM.

Example input:

```json
{"query": "budget shift human approval"}
```

Example output:

```json
{
  "ok": true,
  "query": "budget shift human approval",
  "matches": [
    {
      "source": "docs/policies/budget-shift-policy.md",
      "title": "Budget Shift Policy",
      "score": 14,
      "matched_keywords": ["approval", "budget", "human", "shift"],
      "snippet": "Budget shifts can materially affect delivery commitments, client outcomes, and publisher allocation. Any recommendation to move spend between inventory segments, channels, campaigns, or supply sources requires human approval and a recorded rationale."
    }
  ],
  "retrieval": {
    "method": "keyword",
    "policy_dir": "docs/policies",
    "vector_db_used": false,
    "llm_used": false
  }
}
```

## Current Scope

This milestone intentionally does not add frontend UI, approval workflow, LLM orchestration, or action-taking tools. Those live in the separate embedded governance API (`/api/mcp/*`), which reuses these same tool implementations — see [Architecture](./architecture.md) and [MCP Tool Registry](./mcp-tool-registry.md).
