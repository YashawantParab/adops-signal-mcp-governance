"use client";

import Link from "next/link";
import { CheckCircle2, FileClock } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { PageHeader } from "@/components/PageHeader";
import { RiskBadge } from "@/components/RiskBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";
import { WorkflowBar } from "@/components/WorkflowBar";
import { api } from "@/lib/api";
import type { AuditLog, Recommendation } from "@/types";

const GOVERNANCE_ROLES = ["admin", "adops_manager", "product_manager"];

function AuditWorkspace() {
  const { user } = useAuth();
  const canView = GOVERNANCE_ROLES.includes(user.role);
  const searchParams = useSearchParams();
  const initialCampaignId = searchParams.get("campaignId") ?? "All";
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [campaignFilter, setCampaignFilter] = useState(initialCampaignId);
  const [loading, setLoading] = useState(canView);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!canView) return;
    Promise.all([api.auditLogs(), api.recommendations()])
      .then(([auditItems, recommendationItems]) => {
        setLogs(auditItems);
        setRecommendations(recommendationItems);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [canView]);

  const campaignIds = useMemo(
    () => Array.from(new Set([...logs.map((log) => log.campaign_id), ...recommendations.map((item) => item.campaign_id)])).sort(),
    [logs, recommendations]
  );
  const visibleLogs = logs.filter((log) => campaignFilter === "All" || log.campaign_id === Number(campaignFilter));
  const decisions = recommendations.filter(
    (item) => item.status !== "pending" && (campaignFilter === "All" || item.campaign_id === Number(campaignFilter))
  );

  if (!canView) {
    return (
      <>
        <PageHeader
          title="Governance Record"
          subtitle="Verify diagnosis provenance, model execution, recommendation decisions, and accountable human review."
        />
        <WorkflowBar currentStep={4} />
        <EmptyState
          title="Restricted to authorized roles"
          body={`Your role (${user.role.replace("_", " ")}) does not include governance record access. Sign in as an AdOps Manager or Product Manager to view investigation and decision history.`}
        />
      </>
    );
  }

  if (loading) return <LoadingState label="Loading governance record" />;
  if (error) return <ErrorState message={error} />;

  return (
    <>
      <PageHeader
        title="Governance Record"
        subtitle="Verify diagnosis provenance, model execution, recommendation decisions, and accountable human review."
      />
      <WorkflowBar currentStep={4} />

      <section className="panel mb-5 flex flex-col justify-between gap-4 p-4 md:flex-row md:items-center">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-emerald-50 text-emerald-700">
            <CheckCircle2 size={19} aria-hidden="true" />
          </div>
          <div>
            <p className="font-semibold">{visibleLogs.length} investigations · {decisions.length} recorded decisions</p>
            <p className="mt-1 text-sm text-slate-500">Evidence and approvals are retained as separate accountable events.</p>
          </div>
        </div>
        <label>
          <span className="sr-only">Filter governance record by campaign</span>
          <select
            value={campaignFilter}
            onChange={(event) => setCampaignFilter(event.target.value)}
            className="focus-ring w-full rounded-md border border-line bg-white px-3 py-2 text-sm md:w-48"
          >
            <option value="All">All campaigns</option>
            {campaignIds.map((campaignId) => (
              <option key={campaignId} value={campaignId}>
                Campaign {campaignId}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="panel mb-5 overflow-hidden">
        <div className="border-b border-line px-5 py-4">
          <h2 className="font-semibold">Human decision history</h2>
          <p className="mt-1 text-sm text-slate-500">Approval outcomes with reviewer rationale and timestamp.</p>
        </div>
        {decisions.length ? (
          <div className="divide-y divide-line">
            {decisions.map((item) => (
              <div key={item.id} className="grid gap-3 px-5 py-4 lg:grid-cols-[160px_1fr_220px] lg:items-center">
                <div>
                  <Link href={`/campaigns/${item.campaign_id}`} className="text-sm font-semibold text-accent hover:text-teal-700">
                    Campaign {item.campaign_id}
                  </Link>
                  <div className="mt-2">
                    <RiskBadge value={item.status} />
                  </div>
                </div>
                <div>
                  <p className="font-medium">{item.title}</p>
                  <p className="mt-1 text-sm leading-5 text-slate-600">{item.decision_reason}</p>
                </div>
                <div className="text-sm text-slate-500 lg:text-right">
                  <p>User {item.decided_by_user_id}</p>
                  <p className="mt-1">{item.decided_at ? new Date(item.decided_at).toLocaleString() : "Time unavailable"}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="px-5 py-6 text-sm text-slate-500">No human decisions have been recorded for this view.</div>
        )}
      </section>

      <section className="panel overflow-hidden">
        <div className="flex items-center gap-3 border-b border-line px-5 py-4">
          <FileClock className="text-slate-500" size={18} aria-hidden="true" />
          <div>
            <h2 className="font-semibold">Agent execution history</h2>
            <p className="mt-1 text-sm text-slate-500">Queries, bounded tools, runtime mode, confidence, and diagnosis output.</p>
          </div>
        </div>
        {visibleLogs.length === 0 ? (
          <EmptyState title="No investigations in this view" body="Run a campaign diagnosis to create the first evidence trace." />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-line text-sm">
              <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Time / campaign</th>
                  <th className="px-4 py-3">Operator question</th>
                  <th className="px-4 py-3">Execution</th>
                  <th className="px-4 py-3">Evidence tools</th>
                  <th className="px-4 py-3">Diagnosis</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line bg-white">
                {visibleLogs.map((log) => (
                  <tr key={log.id} className="align-top hover:bg-slate-50">
                    <td className="whitespace-nowrap px-4 py-4">
                      <Link className="font-semibold text-ink hover:text-accent" href={`/campaigns/${log.campaign_id}`}>
                        Campaign {log.campaign_id}
                      </Link>
                      <p className="mt-1 text-xs text-slate-500">{new Date(log.created_at).toLocaleString()}</p>
                      <p className="mt-1 max-w-40 truncate font-mono text-xs text-slate-400">{log.request_id ?? `audit-${log.id}`}</p>
                    </td>
                    <td className="max-w-xs px-4 py-4 text-slate-700">{log.user_query}</td>
                    <td className="whitespace-nowrap px-4 py-4">
                      <p className="font-medium">{log.execution_mode === "llm_rag" ? log.model_name : "Fallback"}</p>
                      <p className="mt-1 text-xs capitalize text-accent">{log.query_intent.replaceAll("_", " ")}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        {Math.round(log.confidence_score * 100)}% · {log.latency_ms} ms
                      </p>
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex max-w-sm flex-wrap gap-1">
                        {log.tools_called.map((tool) => (
                          <span key={tool} className="rounded-md border border-line bg-slate-50 px-2 py-1 text-xs">
                            {tool}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="max-w-lg px-4 py-4 leading-6 text-slate-700">{log.diagnosis}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

export default function AuditLogsPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading governance record" />}>
      <AuditWorkspace />
    </Suspense>
  );
}
