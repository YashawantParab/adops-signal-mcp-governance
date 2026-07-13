# Demo Script

Two timed walkthroughs of the same flow — Campaign 1045 (RheinAuto CTV Launch), which is under-delivering — plus talking points for a Senior AI PM interview. Both versions exercise the **MCP Governance** surface (`/mcp-governance`), the deliverable this documentation pass is built around. All data is seeded and synthetic; see [Dataset Disclaimer](./architecture.md#dataset-disclaimer).

> A separate, previously recorded [two-minute demo video](./demo/adops-signal-2-minute-demo.mp4) and its [narration script](./demo/narration.txt) cover the earlier `/agent` diagnosis-and-recommendation workflow (also on Campaign 1045, a different code path than MCP governance). This script is the current, primary walkthrough of the MCP governance control plane described in the [product case study](./product-case-study.md).

Before recording or presenting: `docker compose up --build`, sign in with the demo credentials from [README → Local Setup](../README.md#local-setup), and confirm Campaign 1045 has a pending recommendation by reseeding if needed (`docker compose exec backend python seed.py`).

## 3-Minute Version

**0:00–0:25 — Open MCP Dashboard.**
Open `/mcp-governance`. "This is a governance control plane for an AdOps agent — it doesn't just answer questions, it decides when a proposed action needs a human before it can happen."

**0:25–0:45 — Show tool/risk/approval metrics.**
Point at the dashboard tiles: run volume, risk mix, pending approvals, blocked actions, tool failure rates. "Before I run anything, this is the operating picture: how much the agent has done, how risky it's been, and what's still waiting on a human."

**0:45–1:00 — Open Agent Console.**
Go to `/mcp-governance/agent`. "Campaign 1045, RheinAuto's CTV launch, is behind pacing. I'm going to let the agent investigate it live."

**1:00–1:45 — Run campaign 1045.**
Submit campaign `1045` with a query like "Why is RheinAuto behind pacing and what should we do?" "The agent calls five read-only MCP tools in sequence — campaign health, pacing trend, VAST validation, brand-safety findings, and a keyword search over our governance policy docs. Every call is logged with its input, output, and latency before any conclusion is reached." Point at the tool timeline as it appears.

**1:45–2:15 — Show risk score and recommendation.**
"The risk engine is a deterministic, additive scoring function — not a model guess. Pacing risk, VAST error count, and brand-safety severity roll up into a 0–100 score. Campaign 1045 lands in the HIGH band, so the agent does not act — it opens an approval request instead of returning a bare recommendation." Open the run detail page and show the risk score, band, and the newly created approval request.

**2:15–2:35 — Open Decision Queue, show the approval request.**
Go to `/mcp-governance/approvals`. "This is where a human — an AdOps Manager or Admin, role-gated — decides. Nothing here can approve itself." Open the pending request, approve it with a rationale. "That decision — who approved it, when, and why — is now permanently attached to this run."

**2:35–2:55 — Open Tool Registry, explain controlled tool access.**
Go to `/mcp-governance/tools`. "Every tool the agent can call is listed here with its permission level, risk level, and live call/failure history. There is no tool in this registry that can mutate a campaign, budget, or bid — that boundary is enforced by what's registered, not by hoping the agent behaves."

**2:55–3:00 — Close.**
"The agent's only side effects are governance records — a run, a risk score, and a decision that a human made and can be held accountable for."

## 5-Minute Version

Everything in the 3-minute version, plus:

**0:00–0:20 — Set up the stakes (before opening the app).**
"AdOps teams are starting to give agents real tools — query campaign data, check creative validation, search policy. The open question isn't whether the agent can find the right answer. It's what happens the moment its answer implies an action with financial or brand-safety consequences. This project is my answer to that question, built as a working system, not a slide."

**0:20–1:05 — Open MCP Dashboard, show tool/risk/approval metrics (same as 3-min open).**

**1:05–1:20 — Open Agent Console (same as 3-min).**

**1:20–2:05 — Run campaign 1045 (same as 3-min).**

**2:05–2:35 — Show risk score and recommendation (same as 3-min).**

**2:35–3:00 — Open Decision Queue, show the approval request; Open Tool Registry, explain controlled tool access (same as 3-min).**

**3:00–3:20 — Add architecture explanation.**
Briefly sketch it: "Next.js frontend, FastAPI backend, Postgres database. The frontend never talks to the backend directly — it goes through a same-origin proxy route, so there's one auth boundary, not two. The MCP tool layer sits inside the backend and reuses the same service functions a standalone MCP server (connectable from MCP Inspector or Claude Desktop) also calls, so behavior can't silently diverge between the two surfaces." Point to [Architecture](./architecture.md) if asked for the diagram.

**3:20–3:40 — Explain Render/Vercel/Neon deployment.**
"This is deployed for real, not just running locally: the frontend is on Vercel, the backend is a Docker image on Render, and the database is managed Postgres on Neon with `pgvector`. The Render free tier can cold-start, so the frontend has a 'waking up' retry state instead of just showing a broken page on the first request."

**3:40–4:00 — Explain why MCP matters.**
"MCP gives tool calls a standard, inspectable shape — name, input schema, output contract. That's what makes a tool registry, a call log, and a risk engine keyed off tool metadata something you build once and reuse for every future agent, instead of bespoke governance code per agent."

**4:00–4:25 — Contrast with the blocked case.**
Run a second investigation against campaign `1046` (NordicStream), which has a rejected creative. "This one scores CRITICAL, not HIGH — a rejected creative that must not serve forces the ceiling regardless of the additive score. Notice the difference: HIGH creates an approval request for a human to decide; CRITICAL creates a blocked action that never even reaches the approval queue, because some things shouldn't be one human's call to override casually." Show the `blocked_actions` record on the run detail page.

**4:25–4:45 — Explain what is simulated.**
"To be direct about what's real and what isn't: the workflow, the risk engine, the approval gate, and the audit trail are all real, running code. The campaign data behind them is a synthetic portfolio environment generated by a seed script — there's no live ad server, SSP, or DSP connected, and no real advertiser or customer data anywhere in this system."

**4:45–5:00 — Explain what would be productionized next.**
"Two things, in order: replace keyword policy search with real retrieval over an expanded, reviewed policy corpus, and connect a read-only real data source behind the same tool contracts, so the governance layer proves out against live data before anyone considers write access."

## Interview Talking Points

Use these as answers to likely follow-up questions, not as a script to recite.

- **"Why build governance instead of another agent demo?"** Most agent demos stop at "the agent found the right answer." The harder product problem is deciding which of the agent's outputs are safe to auto-apply, which need a human, and which should never happen without escalation — and then being able to prove, after the fact, that the process was followed. That's a governance/trust problem, and it's the one enterprises actually block agent rollouts on.
- **"Why MCP specifically?"** MCP gives tool calls a standard, inspectable shape — name, input schema, output contract — instead of ad hoc function-calling glue. That standardization is what makes a tool registry, a call log, and a risk engine keyed off tool metadata *possible* to build generically, rather than one-off per agent. It's also what lets the same tools be consumed by more than one client (this product's own UI, or an external MCP host like Claude Desktop) without re-implementing the business logic.
- **"Is the risk scoring 'AI'?"** No, and that's deliberate. It's a transparent, additive rule engine over evidence the tools already returned. I did not want the layer that decides "does a human need to see this" to itself be an opaque model call — that would just move the trust problem one level down instead of solving it.
- **"What would you build next?"** Two things, in order: (1) replace the keyword policy search with real retrieval and expand the policy corpus with actual reviewed governance documents, and (2) connect a real read-only data source behind the same tool contracts, so the governance layer proves out against live data before anyone considers write access.
- **"What's the actual product wedge?"** Not "AI diagnoses campaigns" — every AdOps vendor claims that. The wedge is "AI agents get real tool access to your ad stack, and every action they could take is scored, logged, and gated the same way regardless of which agent or which tool called it." That's infrastructure a platform team buys once and every future agent inherits, not a single point solution.

## What Not To Overclaim

Say these things plainly if asked, don't wait to be pressed:

- This has **no live ad server, SSP, or DSP integration**. Every number the agent reads comes from a seeded SQLite/PostgreSQL database (`backend/seed.py`).
- This is **not deployed in production** and has **no real customer usage** — it is a portfolio-grade working prototype.
- The risk engine is **deterministic and rule-based**, not a trained model — don't describe it as "the AI decides risk."
- The standalone MCP server (`mcp-server/`) is a **local milestone**, run manually via stdio/Streamable HTTP — there is no hosted, authenticated MCP endpoint for external clients yet.
- `search_policy_context` is **keyword matching over four markdown files**, not a production policy engine or a vector/RAG system.
- The approval workflow enforces role checks and rationale, but authentication is **demo credentials, not enterprise SSO** — say so if asked how this would harden for a real deployment.

See [Product Case Study → Limitations](./product-case-study.md#limitations) for the full list.
