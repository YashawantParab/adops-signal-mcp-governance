# Product Use Cases

## Priority Framework

Use cases are ranked by operational frequency, revenue exposure, evidence availability, and reversibility of action.

| Priority | Use case | User | Outcome | Automation boundary |
|---:|---|---|---|---|
| P0 | Diagnose campaign underdelivery | AdOps Manager | Agreed root cause in minutes | Recommendation only |
| P0 | Validate VAST/creative readiness | Publisher Ops | Prevent non-serving creative | Validation only |
| P0 | Produce client-safe explanation | Customer Success | Faster, consistent update | Draft only |
| P1 | Assess recovery feasibility | Campaign Manager | Reforecast before escalation | Recommendation only |
| P1 | Review and approve action | AdOps Lead | Controlled operational change | Human approval |
| P1 | Audit agent decisions | Product/Compliance | Inspect evidence and model trace | Read only |
| P2 | Detect recurring failure patterns | Product Manager | Prioritize platform improvements | Aggregated insight |
| P2 | Proactively alert delivery risk | AdOps Manager | Intervene before SLA risk | Alert only |

## UC-01: Diagnose Underdelivery

**Trigger:** Campaign pacing falls below the risk threshold or an operator asks a question.

**Flow:**

1. Operator selects a campaign.
2. Signal retrieves pacing, setup, targeting, inventory, bid, creative, and portfolio-pressure evidence.
3. RAG retrieves relevant operating playbooks.
4. The LLM returns structured, ranked causes with evidence IDs.
5. Unsupported causes are rejected.
6. Recommendations enter a pending approval state.
7. The complete trace is written to the audit log.

**Success:** The primary cause matches expert judgment and every claim is inspectable.

## UC-02: Creative And VAST Triage

**Trigger:** A creative is rejected, validation errors increase, or delivery drops after a creative change.

**Success:** Operations can distinguish approval failure, timeout, missing media, companion asset, and tracking errors and route the issue to the correct owner.

## UC-03: Client-Safe Communication

**Trigger:** Customer Success needs a campaign update.

**Guardrail:** The draft excludes publisher floor prices, raw bid-loss reasons, internal tools, and validation traces.

## UC-04: Recommendation Approval

**Trigger:** Signal proposes a targeting, bid, frequency, flight, inventory, or creative change.

**Guardrail:** Only AdOps Manager or Admin roles can approve or reject. A decision requires rationale and records reviewer identity and timestamp. The prototype does not mutate a live campaign.

## Negative Use Cases

- Signal must not invent missing campaign data.
- Signal must not execute a bid or targeting change without a downstream approval integration.
- Signal must not expose internal auction economics in client communication.
- Signal must not replace incident ownership or contractual decision rights.
