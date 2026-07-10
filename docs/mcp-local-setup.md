# MCP Local Setup

This repository exposes the first MCP governance milestone as a separate Python server under `mcp-server/`.
It reuses the existing SignalOps AI backend models, database configuration, and campaign health service.

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

## Current Scope

This milestone intentionally does not add frontend UI, approval workflow, LLM orchestration, or action-taking tools.
