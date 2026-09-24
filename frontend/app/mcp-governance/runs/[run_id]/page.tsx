"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, ShieldAlert, ShieldCheck, ThumbsDown, ThumbsUp } from "lucide-react";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { PageHeader } from "@/components/PageHeader";
import { RiskBadge } from "@/components/RiskBadge";
import { ErrorState, LoadingState } from "@/components/StateViews";
import { api, DEMO_VIEWER_ROLE, formatDateTime, formatReviewer } from "@/lib/api";
import type { MCPAgentRunDetail } from "@/types";

export default function MCPGovernanceRunDetailPage() {
  const params = useParams<{ run_id: string }>();
  const runId = Number(params.run_id);
  const { user } = useAuth();
  const isDemoViewer = user?.role === DEMO_VIEWER_ROLE;

  const [run, setRun] = useState<MCPAgentRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [comment, setComment] = useState("");
  const [submittingFeedback, setSubmittingFeedback] = useState(false);

  async function sendFeedback(rating: "up" | "down") {
    if (isDemoViewer) return;
    setSubmittingFeedback(true);
    try {
      await api.submitRunFeedback(runId, rating, comment.trim() || undefined);
      setComment("");
      load();
    } catch (err) {
      setError(err);
    } finally {
      setSubmittingFeedback(false);
    }
  }

  function load() {
    if (!Number.isFinite(runId)) {
      setError(new Error(`Invalid run id: ${params.run_id}`));
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    api
      .mcpRunDetail(runId)
      .then(setRun)
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(load, [runId]);

  if (loading) return <LoadingState label="Loading governance record" />;
  if (error || !run) return <ErrorState error={error ?? new Error("Run not found")} onRetry={load} />;

  return (
    <>
      <div className="mb-4">
        <Link href="/mcp-governance" className="focus-ring inline-flex items-center text-sm font-semibold text-accent hover:text-teal-700">
          <ArrowLeft className="mr-1" size={15} aria-hidden="true" />
          Back to MCP Governance Dashboard
        </Link>
      </div>
      <PageHeader
        title={`Governance Record · Run #${run.id}`}
        subtitle="Full record of a governed MCP agent run: user request, evidence tool calls, policy checks, risk scoring, and approval outcome."
      />

      <section className="panel mb-6 rounded-md p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase text-accent">User Query</p>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-700">&ldquo;{run.user_query}&rdquo;</p>
            <p className="mt-3 text-xs font-semibold uppercase text-accent">Campaign</p>
            <Link href={`/campaigns/${run.campaign_id}`} className="mt-1 block text-sm font-semibold text-ink hover:text-accent">
              Campaign {run.campaign_id}
              {run.campaign_name ? ` · ${run.campaign_name}` : ""}
            </Link>
          </div>
          <div className="flex flex-col items-end gap-2">
            <RiskBadge value={run.status} />
            <RiskBadge value={run.risk_level} />
          </div>
        </div>
        <div className="mt-4 grid gap-2 border-t border-line pt-4 text-xs text-slate-500 sm:grid-cols-2">
          <p>Created {formatDateTime(run.created_at)}</p>
          <p>Completed {run.completed_at ? formatDateTime(run.completed_at) : "Not completed"}</p>
        </div>
      </section>

      <section className="panel mb-6 rounded-md p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <p className="text-xs font-semibold uppercase text-accent">Execution</p>
          <RiskBadge value={run.execution_mode} />
        </div>
        {run.execution_mode === "llm_mcp_agent" ? (
          <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <p className="text-xs font-medium uppercase text-slate-500">Provider / model</p>
              <p className="mt-1 font-medium text-ink">
                {run.llm_provider ?? "unknown"}
                {run.model_name ? ` · ${run.model_name}` : ""}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium uppercase text-slate-500">Steps used</p>
              <p className="mt-1 font-medium text-ink">
                {run.steps_used ?? "—"}
                {run.max_steps ? ` / ${run.max_steps} max` : ""}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium uppercase text-slate-500">Tokens (in / out / total)</p>
              <p className="mt-1 font-medium text-ink">
                {run.input_tokens ?? "—"} / {run.output_tokens ?? "—"} / {run.total_tokens ?? "—"}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium uppercase text-slate-500">Estimated cost</p>
              <p className="mt-1 font-medium text-ink">
                {run.estimated_cost_usd != null ? `$${run.estimated_cost_usd.toFixed(4)}` : "not available"}
              </p>
            </div>
          </div>
        ) : (
          <p className="mt-3 text-sm text-slate-600">
            Ran the deterministic rule-based orchestration instead of the governed LLM + MCP agent.
            {run.fallback_reason ? (
              <>
                {" "}
                Reason: <span className="font-mono text-xs">{run.fallback_reason}</span>.
              </>
            ) : null}
          </p>
        )}
      </section>

      {run.gate_decisions.length ? (
        <section className="panel mb-6 rounded-md p-5">
          <p className="text-xs font-semibold uppercase text-accent">System 1</p>
          <h2 className="mt-1 text-base font-semibold">Decision Gates</h2>
          <div className="mt-3 space-y-2">
            {run.gate_decisions.map((gate) => (
              <div key={gate.id} className="rounded-md border border-line p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-ink">{gate.decision_point.replaceAll("_", " ")}</span>
                  <div className="flex items-center gap-2">
                    <span className="rounded-md border border-line bg-slate-50 px-2 py-1 text-xs font-medium uppercase text-slate-600">
                      {gate.gate_type}
                      {gate.model_name ? ` · ${gate.model_name}` : ""}
                    </span>
                    <RiskBadge value={gate.final_decision} />
                  </div>
                </div>
                <p className="mt-2 text-xs text-slate-500">
                  Gate said <span className="font-medium text-slate-700">{gate.decision}</span>
                  {gate.confidence != null ? ` at ${(gate.confidence * 100).toFixed(0)}% confidence` : ""}
                  {gate.rule_floor ? (
                    <>
                      {" "}
                      · rule floor <span className="font-medium text-slate-700">{gate.rule_floor}</span>
                      {gate.final_decision !== gate.rule_floor ? " (gate escalated)" : ""}
                    </>
                  ) : null}
                  {" "}· {gate.latency_ms} ms
                </p>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {run.execution_mode === "llm_mcp_agent" && run.client_safe_brief_status ? (
        <section className="panel mb-6 rounded-md p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs font-semibold uppercase text-accent">Client-Safe Brief</p>
            <RiskBadge value={run.client_safe_brief_status} />
          </div>
          {run.client_safe_brief_status === "safe" && run.client_safe_brief ? (
            <p className="mt-3 text-sm leading-6 text-slate-700">{run.client_safe_brief}</p>
          ) : (
            <p className="mt-3 text-sm text-slate-600">
              Withheld pending human review - the client-safe-brief gate did not classify the drafted brief as safe to
              release automatically.
            </p>
          )}
        </section>
      ) : null}

      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <section className="panel rounded-md p-5">
          <p className="text-xs font-semibold uppercase text-accent">Governance</p>
          <h2 className="mt-1 text-base font-semibold">Risk Score</h2>
          <div className="mt-3 flex items-end gap-3">
            <p className="text-4xl font-semibold text-ink">{run.risk_score}</p>
            <p className="pb-1 text-sm text-slate-500">/ 100</p>
          </div>
          <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className={`h-full rounded-full ${
                run.risk_level === "CRITICAL"
                  ? "bg-red-600"
                  : run.risk_level === "HIGH"
                    ? "bg-red-400"
                    : run.risk_level === "MEDIUM"
                      ? "bg-amber-400"
                      : "bg-emerald-500"
              }`}
              style={{ width: `${Math.min(Math.max(run.risk_score, 0), 100)}%` }}
            />
          </div>
        </section>

        <section className="panel rounded-md p-5">
          <p className="text-xs font-semibold uppercase text-accent">Governance</p>
          <h2 className="mt-1 flex items-center gap-2 text-base font-semibold">
            {run.approval_requests.some((item) => item.status === "pending") ? (
              <>
                <ShieldAlert size={18} className="text-amber-700" aria-hidden="true" /> Approval Pending
              </>
            ) : run.approval_required ? (
              <>
                <ShieldCheck size={18} className="text-emerald-700" aria-hidden="true" /> Approval Decided
              </>
            ) : (
              <>
                <ShieldCheck size={18} className="text-emerald-700" aria-hidden="true" /> No Approval Required
              </>
            )}
          </h2>
          {run.approval_requests.length ? (
            <div className="mt-3 space-y-2">
              {run.approval_requests.map((approval) => (
                <div key={approval.id} className="rounded-md border border-line p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <RiskBadge value={approval.status} />
                    <RiskBadge value={approval.risk_level} />
                  </div>
                  <p className="mt-2 text-slate-700">{approval.proposed_action}</p>
                  <p className="mt-2 text-xs text-slate-500">
                    {approval.status === "pending"
                      ? "Awaiting authorized reviewer"
                      : `${formatReviewer(approval.reviewer_name, null, approval.reviewer_id)} · ${
                          approval.reviewed_at ? formatDateTime(approval.reviewed_at) : "Time unavailable"
                        }`}
                  </p>
                  <Link
                    href="/mcp-governance/approvals"
                    className="mt-2 inline-block text-xs font-semibold text-accent hover:text-teal-700"
                  >
                    Open in decision queue
                  </Link>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-sm text-slate-500">This run did not require human approval.</p>
          )}
        </section>
      </div>

      <section className="panel mb-6 rounded-md p-5">
        <p className="text-xs font-semibold uppercase text-accent">Outcome</p>
        <h2 className="mt-1 text-base font-semibold">Final Recommendation</h2>
        <p className="mt-3 text-sm leading-6 text-slate-700">{run.final_recommendation}</p>
      </section>

      {run.blocked_actions.length ? (
        <section className="panel mb-6 rounded-md border-red-200 bg-red-50 p-5">
          <p className="text-xs font-semibold uppercase text-accent">Governance</p>
          <h2 className="mt-1 flex items-center gap-2 text-base font-semibold">
            <ShieldAlert size={18} className="text-red-700" aria-hidden="true" />
            Blocked Actions
          </h2>
          <div className="mt-3 space-y-2">
            {run.blocked_actions.map((action) => (
              <div key={action.id} className="rounded-md border border-red-200 bg-white p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-medium">{action.tool_name.replaceAll("_", " ")}</p>
                  <RiskBadge value={action.risk_level} />
                </div>
                <p className="mt-2 text-slate-600">{action.reason}</p>
                <p className="mt-2 text-xs text-slate-400">{formatDateTime(action.created_at)}</p>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="panel mb-6 rounded-md p-5">
        <p className="text-xs font-semibold uppercase text-accent">Governance</p>
        <h2 className="mt-1 text-base font-semibold">Policy Checks</h2>
        {run.policy_checks.length ? (
          <div className="mt-3 space-y-2">
            {run.policy_checks.map((check) => (
              <div key={check.id} className="rounded-md border border-line p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium text-ink">{check.policy_name}</p>
                  <RiskBadge value={check.result} />
                </div>
                <p className="mt-2 text-xs text-slate-500">{check.citation}</p>
                {check.matched_rules.length ? (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {check.matched_rules.map((rule) => (
                      <span key={String(rule)} className="rounded-md border border-line bg-slate-50 px-2 py-1 text-xs">
                        {String(rule)}
                      </span>
                    ))}
                  </div>
                ) : null}
                <p className="mt-2 text-xs text-slate-400">{formatDateTime(check.created_at)}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-3 text-sm text-slate-500">No policy checks were recorded for this run.</p>
        )}
      </section>

      <section className="panel rounded-md p-5">
        <p className="text-xs font-semibold uppercase text-accent">Governance</p>
        <h2 className="mt-1 text-base font-semibold">MCP Tool Call Timeline</h2>
        {run.tool_calls.length ? (
          <ol className="mt-3 space-y-2">
            {run.tool_calls.map((call, index) => (
              <li key={call.id} className="flex items-start gap-3 rounded-md border border-line p-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-line text-xs font-semibold text-slate-600">
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md border border-line bg-slate-50 px-2 py-1 text-xs font-medium text-slate-700">
                      {call.tool_name}
                    </span>
                    <RiskBadge value={call.status} />
                    <span className="text-xs text-slate-400">{call.latency_ms} ms</span>
                    <span className="text-xs text-slate-400">{formatDateTime(call.created_at)}</span>
                  </div>
                  <details className="mt-2 text-xs text-slate-600">
                    <summary className="cursor-pointer font-medium text-slate-500">Input / output payload</summary>
                    <pre className="mt-2 overflow-x-auto rounded-md bg-slate-50 p-2 text-xs">
                      {JSON.stringify({ input: call.input_json, output: call.output_json }, null, 2)}
                    </pre>
                  </details>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-3 text-sm text-slate-500">No MCP tool calls were recorded for this run.</p>
        )}
      </section>

      <section className="panel mt-6 rounded-md p-5">
        <p className="text-xs font-semibold uppercase text-accent">Feedback</p>
        <h2 className="mt-1 text-base font-semibold">Was this diagnosis useful?</h2>
        {isDemoViewer ? (
          <p className="mt-3 text-sm text-slate-600">
            Public demo is read-only.{" "}
            <Link href="/" className="font-semibold text-accent hover:text-teal-700">
              Use the full demo login
            </Link>{" "}
            to leave feedback.
          </p>
        ) : (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              type="text"
              placeholder="Optional comment"
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              className="focus-ring w-72 rounded-md border border-line px-3 py-2 text-sm"
            />
            <button
              type="button"
              onClick={() => sendFeedback("up")}
              disabled={submittingFeedback}
              className="focus-ring inline-flex items-center rounded-md border border-line px-3 py-2 text-sm font-semibold text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
            >
              <ThumbsUp className="mr-2" size={15} aria-hidden="true" />
              Helpful
            </button>
            <button
              type="button"
              onClick={() => sendFeedback("down")}
              disabled={submittingFeedback}
              className="focus-ring inline-flex items-center rounded-md border border-line px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
            >
              <ThumbsDown className="mr-2" size={15} aria-hidden="true" />
              Not helpful
            </button>
          </div>
        )}
        {run.feedback.length ? (
          <ul className="mt-4 space-y-2">
            {run.feedback.map((item) => (
              <li key={item.id} className="flex items-start gap-2 rounded-md border border-line p-3 text-sm">
                {item.rating === "up" ? (
                  <ThumbsUp size={15} className="mt-0.5 shrink-0 text-emerald-600" aria-hidden="true" />
                ) : (
                  <ThumbsDown size={15} className="mt-0.5 shrink-0 text-red-600" aria-hidden="true" />
                )}
                <div>
                  <p className="text-slate-700">{item.comment || <span className="text-slate-400">No comment</span>}</p>
                  <p className="mt-1 text-xs text-slate-400">
                    {item.reviewer_name ?? "Reviewer"} · {formatDateTime(item.created_at)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </>
  );
}
