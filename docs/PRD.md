# Product Requirements: AdOps Signal

## Product Thesis

CTV underdelivery is not primarily a “find the metric” problem. It is a cross-system reasoning problem: operators must combine pacing, campaign configuration, eligible supply, creative quality, auction economics, and organizational approval before they can act.

AdOps Signal should reduce time to an evidence-backed decision while preserving operator accountability.

## Users And Jobs

| User | Job to be done | Current cost |
|---|---|---|
| AdOps Manager | Find the leading delivery constraint and next action | Dashboard switching, SQL requests, escalation |
| Publisher Operations | Separate supply, request, and creative failure | Manual log inspection and ownership ambiguity |
| Customer Success | Explain the issue without exposing internal mechanics | Rewriting technical findings under time pressure |
| Product Manager | Find recurring operational failure patterns | Fragmented incident knowledge |

## MVP Outcome

For a seeded or connected campaign, an authenticated operator can obtain a ranked diagnosis with cited evidence, review recommended actions, generate client-safe language, and audit the complete agent trace.

## Scope

- Campaign health and pacing.
- Targeting and eligible inventory analysis.
- Request failure distribution and shared inventory pressure.
- Creative approval and VAST validation.
- Bid/floor competitiveness.
- LLM reasoning with RAG guidance.
- Deterministic provider fallback.
- Role-based recommendation approval.
- Audit logs, metrics, and ROI model.

## Out Of Scope

- Direct mutation of live campaign settings.
- Autonomous budget or bid optimization.
- Contractual makegood decisions.
- Production customer data.
- Claims of validated customer adoption.

## Product Principles

1. Evidence before eloquence.
2. The model proposes; accountable humans decide.
3. General playbooks cannot substitute for campaign facts.
4. Degraded service must be visible, not hidden.
5. Client communication and internal diagnosis are different products.
6. Value must be measured through time saved and delivery recovered.

## Functional Requirements

- Every root cause cites valid evidence IDs.
- Every diagnosis reports model, mode, prompt version, latency, and retrieved sources.
- High-impact recommendations require approval.
- Role permissions are enforced by the API.
- LLM failure returns a clearly marked grounded fallback.
- Audit history persists across production restarts.
- ROI assumptions remain editable and transparent.

## Success Metrics

### North Star

Median time from delivery-risk signal to operator-confirmed root cause.

### Supporting Metrics

- Expert agreement with top-ranked cause.
- Evidence citation precision.
- Recommendations approved without revision.
- Number of systems/handoffs per incident.
- Client-summary edit distance.
- Recovered delivery after approved intervention.

### Counter-Metrics

- Unsupported claims.
- Incorrect high-impact approvals.
- Incidents where Signal increases investigation time.
- Sensitive internal details in client summaries.
- Model cost per resolved incident.

## Acceptance Criteria

- Docker Compose starts the frontend, backend, and PostgreSQL.
- Authentication is required for product APIs.
- Five seeded campaigns produce inspectable diagnoses.
- LLM mode activates when a valid key is configured.
- Fallback mode works without paid APIs.
- RAG returns relevant playbooks.
- Fifteen golden cases meet the 90% quality floor.
- Recommendation permissions and audit logs work.
- Health, readiness, metrics, CI, migrations, and deployment configuration exist.

## Rollout

1. **Internal shadow mode:** Compare Signal with expert diagnosis; no actions.
2. **Assisted pilot:** Operators use the UI; recommendations remain approval-only.
3. **Connected workflow:** Write approved changes to a staging campaign system.
4. **Controlled automation:** Automate only reversible, low-risk actions with rollback.

## Research And Assumptions

The concept assumes campaign data can be joined reliably and that operators value cited evidence. These are hypotheses until real interviews and a controlled pilot are completed. See [USER_RESEARCH.md](./USER_RESEARCH.md).
