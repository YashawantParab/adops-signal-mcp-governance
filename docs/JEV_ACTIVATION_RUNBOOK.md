# Jev Activation Runbook

This is the exact, future process for turning on live Jev (TypeSafe AI System One)
execution once TypeSafe access is granted. Nothing in this document has been executed
yet — TypeSafe's early-access waitlist is currently full and no `TYPESAFE_API_KEY` is
available. See [`docs/jev-integration-notes.md`](./jev-integration-notes.md) for what is
confirmed about the API contract, and the [README's Jev section](../README.md#jev-typesafe-ai-system-one)
for the product framing (LLM = System 2, Jev = System 1, Rules = safety floor, Human =
final authority).

## Prerequisites already in place (nothing further to build)

- `typesafe-sdk==0.7.1` is a pinned dependency in `backend/requirements.txt`.
- `JevGate` (`backend/app/gates/jev_gate.py`) is implemented against the real SDK
  contract and integrated into the standard `jev → llm → rules` fallback chain.
- The deterministic safety floor (`apply_rule_floor`, `apply_confidence_floor`) applies
  to Jev exactly as it does to every other gate — this cannot be reconfigured away.
- `python -m app.gates.jev_readiness` and `python -m evals.gate_evaluation --provider jev --live`
  already exist and are ready to run.

## Steps to go live

1. **Receive TypeSafe access.** Confirmation that the early-access waitlist request has
   been approved (via TypeSafe's own onboarding flow — outside this repo).

2. **Create an API key** in the TypeSafe dashboard, scoped to the account that has Jev
   access.

3. **Configure `TYPESAFE_API_KEY` locally.** Add it to `backend/.env` (never commit it —
   `.env` is already gitignored; `.env.example` holds only a placeholder). Optionally set
   `JEV_MODEL` (defaults to `jev-latest`) and `JEV_TIMEOUT_SECONDS` (defaults to `10`).

4. **Run the readiness check:**
   ```bash
   cd backend
   python -m app.gates.jev_readiness
   ```
   This makes exactly one lightweight `client.models.list()` call (never a billed
   `system_one()` call) to confirm connectivity, and never prints the key itself. Expect
   `Overall: JEV INTEGRATION READY - LIVE ACCESS CONFIRMED`. If it fails, the printed
   reason (auth failure, network error, etc.) says why — do not proceed until it passes.

5. **Execute one smoke-test Jev decision.** The simplest path is a single-provider,
   single-case eval run:
   ```bash
   python -m evals.gate_evaluation --provider jev --live
   ```
   Confirm the printed `Live label:` line says `LIVE (N real Jev call(s) succeeded this
   run)` — the harness refuses to say LIVE otherwise, even with `--live` passed.

6. **Verify the persisted gate decision looks correct.** Open the generated
   `docs/evals/YYYY-MM-DD-gate-report.md`/`.json` and confirm at least one `jev` row has
   `status: ok` with a real `decision`, `confidence`, and `latency_ms` — not `NOT RUN`.
   If you also set `DECISION_GATE_PROVIDER=jev` and ran a real agent investigation via
   the app, check that run's Governance Record page
   (`/mcp-governance/runs/[run_id]`) shows a `gate_type: jev` row with real values, and
   that `gate_decisions.provider`/`model_name`/`confidence` in the database are
   populated (not fabricated placeholders).

7. **Run the full Jev fixture evaluation** (all golden + adversarial cases, not just one):
   ```bash
   python -m evals.gate_evaluation --provider jev --live
   ```
   (Omit `--provider jev` to run Jev alongside LLMGate/RuleGate in the same report for a
   direct side-by-side comparison — recommended for step 9 below.)

8. **Generate metrics.** The eval harness already computes and writes: accuracy (where a
   fixture has an expected label), schema/type-error rate, and p50/p95 latency — see the
   `summary` block in the JSON report. Cost is intentionally left `null` unless a real
   per-call dollar figure is ever added to the SDK's response — see
   `docs/jev-integration-notes.md`'s "NOT PUBLICLY DOCUMENTED" section for why.

9. **Compare Jev vs. LLM vs. Rules.** Run the eval with no `--provider` filter (or run it
   three times, once per provider, with the relevant keys set) and compare the
   `docs/evals/*-gate-report.md` summary table across all three gate types side by side.

10. **Only then consider enabling Jev in a deployed environment.** Set
    `DECISION_GATE_PROVIDER=jev` in that environment's configuration (Render env vars, or
    equivalent) only after steps 1–9 above have been completed and reviewed — never as
    a default, and never without having seen at least one real report.

## Rollback

Jev can be disabled at any time, instantly and without a deploy of new code, by changing
one environment variable:

```bash
DECISION_GATE_PROVIDER=llm     # falls back to the LLM gate
# or
DECISION_GATE_PROVIDER=rules   # falls back to the deterministic-only gate (no key needed)
```

Restart the backend process for the change to take effect (`get_settings()` is
`@lru_cache`d per process). No database migration, code change, or data cleanup is
required — `gate_decisions` rows already record `requested_provider`/`gate_type`
independently per row, so historical Jev-era decisions remain intact and auditable after
rollback. Simply removing `TYPESAFE_API_KEY` also works and is equivalent to `=llm`
falling back further to `=rules` if no LLM key is set either — `JevGate.available` will
report `False` and every future decision will fall through the standard chain, exactly
as it does today with no key configured.
