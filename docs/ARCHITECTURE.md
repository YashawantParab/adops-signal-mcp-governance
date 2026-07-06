# Architecture

## Quality Attributes

The architecture prioritizes evidence integrity, graceful degradation, auditability, and operator control ahead of model novelty.

| Attribute | Design response |
|---|---|
| Reliability | Provider fallback, health/readiness checks, database pre-ping |
| Security | JWT, PBKDF2 passwords, RBAC, security headers, CORS allowlist |
| Explainability | Evidence IDs, tools called, retrieved sources, prompt/model metadata |
| Operability | JSON logs, request IDs, Prometheus metrics, Docker health checks |
| Change safety | Pending recommendations, role-gated approval, required rationale, reviewer, and timestamp |
| Portability | Docker Compose, PostgreSQL primary, SQLite test fallback |
| Evolvability | Provider abstraction, REST contracts, Alembic baseline |

## Components

### Next.js Frontend

- Authenticated operations shell.
- Campaign overview and detailed pacing analysis.
- Diagnosis workspace with root causes, evidence, recommendations, and trace.
- VAST validator.
- Approval queue and audit log.
- Interactive ROI model.

### FastAPI Backend

- Typed REST APIs and Pydantic validation.
- JWT authentication and role authorization.
- Campaign health and auction analytics services.
- LLM/RAG diagnosis orchestrator.
- Recommendation lifecycle.
- Metrics, structured logs, and readiness endpoints.

### Data Layer

- PostgreSQL 16 with pgvector.
- SQLAlchemy ORM.
- Alembic-managed schema baseline.
- Deterministic synthetic fixtures.
- SQLite only for portable tests and local fallback.

## Runtime Topology

See [SYSTEM_DIAGRAMS.md](./SYSTEM_DIAGRAMS.md) for block, sequence, trust-boundary, deployment, and fallback diagrams.

## API Security

- Access tokens include user role, issuer, audience, and expiration.
- Passwords use salted PBKDF2-SHA256.
- Campaign reads require authentication.
- Recommendation mutations require AdOps Manager or Admin.
- Audit logs require AdOps Manager, Product Manager, or Admin.
- Production disables interactive API documentation.
- Secrets are environment variables and never committed.

For a real deployment, replace demo credentials with enterprise SSO/OIDC, rotate signing secrets, add a managed secret store, and stream approval events into the platform audit system.

## Observability

- `GET /health`: liveness.
- `GET /ready`: database readiness and AI mode.
- `GET /metrics`: Prometheus counters and latency histograms.
- `X-Request-ID`: accepted or generated on every request.
- JSON logs include timestamp, level, logger, message, and request ID.
- Agent audits include model, mode, prompt version, latency, and token counts.

## Data Lifecycle

Development Compose sets `SEED_DEMO_DATA=true`. Production must set it to `false`; otherwise startup would intentionally reset demo data. `start.sh` applies migrations before serving traffic.

## Deployment

Recommended production shape:

- Managed TLS and edge protection.
- Independently scalable frontend and backend containers.
- Managed PostgreSQL with pgvector and encrypted backups.
- Restricted outbound access to the selected model provider.
- Central logs, metrics, uptime checks, and alerting.
- CI builds and verifies both containers before deployment.

## Remaining Production Work

- Enterprise SSO and organization tenancy.
- Managed rate limiting and abuse protection.
- Secret manager integration.
- Point-in-time database recovery.
- OpenTelemetry traces.
- Real platform connectors and data freshness SLAs.
- Data retention and deletion policy.
