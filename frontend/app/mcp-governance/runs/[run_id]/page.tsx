"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, ShieldAlert, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { RiskBadge } from "@/components/RiskBadge";
import { ErrorState, LoadingState } from "@/components/StateViews";
import { api, formatDateTime, formatReviewer } from "@/lib/api";
import type { MCPAgentRunDetail } from "@/types";

export default function MCPGovernanceRunDetailPage() {
  const params = useParams<{ run_id: string }>();
  const runId = Number(params.run_id);

  const [run, setRun] = useState<MCPAgentRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

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
    </>
  );
}
