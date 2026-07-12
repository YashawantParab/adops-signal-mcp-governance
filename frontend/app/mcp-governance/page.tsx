"use client";

import Link from "next/link";
import { ArrowRight, Bot, ShieldCheck, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { RiskBadge } from "@/components/RiskBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";
import { StatCard } from "@/components/StatCard";
import { api, formatDateTime, formatNumber, formatPercent } from "@/lib/api";
import type { MCPAgentRun, MCPApprovalRequest, MCPSummary, MCPToolDescriptor } from "@/types";

const RISK_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;
const RISK_BAR_COLOR: Record<string, string> = {
  CRITICAL: "bg-red-600",
  HIGH: "bg-red-400",
  MEDIUM: "bg-amber-400",
  LOW: "bg-emerald-500"
};

const POLICY_ORDER = ["blocked", "approval_required", "review_required", "clear"] as const;

function Bar({ label, value, max, colorClass }: { label: string; value: number; max: number; colorClass: string }) {
  const width = max > 0 ? Math.max((value / max) * 100, value > 0 ? 4 : 0) : 0;
  return (
    <div className="grid grid-cols-[110px_1fr_36px] items-center gap-3 text-sm">
      <span className="truncate text-slate-600">{label}</span>
      <div className="h-2 rounded bg-slate-100">
        <div className={`h-2 rounded ${colorClass}`} style={{ width: `${width}%` }} />
      </div>
      <span className="text-right font-medium text-ink">{value}</span>
    </div>
  );
}

export default function MCPGovernanceDashboardPage() {
  const [summary, setSummary] = useState<MCPSummary | null>(null);
  const [runs, setRuns] = useState<MCPAgentRun[]>([]);
  const [approvals, setApprovals] = useState<MCPApprovalRequest[]>([]);
  const [tools, setTools] = useState<MCPToolDescriptor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  function load() {
    setLoading(true);
    setError(null);
    Promise.all([api.mcpSummary(), api.mcpRuns(), api.mcpApprovals(), api.mcpTools()])
      .then(([summaryData, runsData, approvalsData, toolsData]) => {
        setSummary(summaryData);
        setRuns(runsData);
        setApprovals(approvalsData);
        setTools(toolsData);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  const riskDistribution = useMemo(() => {
    const counts: Record<string, number> = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
    for (const run of runs) {
      if (run.risk_level in counts) counts[run.risk_level] += 1;
    }
    return counts;
  }, [runs]);

  const pendingApprovals = useMemo(() => approvals.filter((item) => item.status === "pending"), [approvals]);
  const recentRuns = runs.slice(0, 8);
  const topTools = useMemo(
    () => [...tools].sort((left, right) => right.call_count - left.call_count).slice(0, 5),
    [tools]
  );

  if (loading) return <LoadingState label="Loading MCP Governance Dashboard" />;
  if (error) return <ErrorState error={error} onRetry={load} />;

  const maxRunsBarValue = Math.max(...Object.values(riskDistribution), 1);
  const maxPolicyBarValue = Math.max(...Object.values(summary?.policy_checks ?? {}), 1);

  return (
    <>
      <PageHeader
        title="MCP Governance Dashboard"
        subtitle="Executive view of governed MCP agent activity: run volume, tool usage, approvals, blocked actions, and policy-grounded outcomes."
      />

      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
        <StatCard
          label="Agent runs"
          value={formatNumber(summary?.total_runs ?? 0)}
          hint={`${formatNumber(summary?.completed_runs ?? 0)} completed · ${formatNumber(summary?.failed_runs ?? 0)} failed`}
        />
        <StatCard
          label="MCP tool calls"
          value={formatNumber(summary?.tool_calls ?? 0)}
          hint={`Avg latency ${summary?.average_tool_latency_ms ?? 0} ms`}
        />
        <StatCard
          label="Approval required"
          value={formatNumber(summary?.approval_requests?.pending ?? 0)}
          hint="Pending human decision"
        />
        <StatCard label="Blocked risky actions" value={formatNumber(summary?.blocked_actions ?? 0)} hint="Escalated, not executed" />
        <StatCard label="Average risk score" value={`${summary?.average_risk_score ?? 0}`} hint="Out of 100, across all runs" />
      </div>

      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <section className="panel rounded-md p-5">
          <h2 className="text-base font-semibold">Risk Distribution</h2>
          <p className="mt-1 text-sm text-slate-500">Agent runs by governance risk level (most recent 100 runs).</p>
          <div className="mt-4 space-y-3">
            {RISK_ORDER.map((level) => (
              <Bar key={level} label={level} value={riskDistribution[level]} max={maxRunsBarValue} colorClass={RISK_BAR_COLOR[level]} />
            ))}
          </div>
        </section>

        <section className="panel rounded-md p-5">
          <h2 className="text-base font-semibold">Policy-Grounded Recommendations</h2>
          <p className="mt-1 text-sm text-slate-500">Policy checks recorded against local governance policy documents, by outcome.</p>
          <div className="mt-4 space-y-3">
            {POLICY_ORDER.map((result) => (
              <Bar
                key={result}
                label={result.replaceAll("_", " ")}
                value={summary?.policy_checks?.[result] ?? 0}
                max={maxPolicyBarValue}
                colorClass={
                  result === "blocked" ? "bg-red-500" : result === "approval_required" ? "bg-amber-400" : result === "review_required" ? "bg-amber-300" : "bg-emerald-500"
                }
              />
            ))}
          </div>
        </section>
      </div>

      <div className="mb-6 grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <section className="panel overflow-hidden rounded-md">
          <div className="flex items-center justify-between border-b border-line px-5 py-4">
            <div>
              <h2 className="font-semibold">Recent Agent Runs</h2>
              <p className="mt-1 text-sm text-slate-500">Latest governed investigations across all campaigns.</p>
            </div>
            <Link href="/mcp-governance/agent" className="focus-ring inline-flex items-center text-sm font-semibold text-accent hover:text-teal-700">
              <Bot className="mr-1" size={15} aria-hidden="true" />
              Run new
            </Link>
          </div>
          {recentRuns.length === 0 ? (
            <div className="p-6">
              <EmptyState title="No agent runs yet" body="Run a governance investigation from the MCP Agent Console." />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-line text-sm">
                <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3">Run</th>
                    <th className="px-4 py-3">Campaign</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Risk</th>
                    <th className="px-4 py-3">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line bg-white">
                  {recentRuns.map((run) => (
                    <tr key={run.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <Link href={`/mcp-governance/runs/${run.id}`} className="font-semibold text-ink hover:text-accent">
                          #{run.id}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {run.campaign_name ?? `Campaign ${run.campaign_id}`}
                      </td>
                      <td className="px-4 py-3">
                        <RiskBadge value={run.status} />
                      </td>
                      <td className="px-4 py-3">
                        <RiskBadge value={run.risk_level} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-500">{formatDateTime(run.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel overflow-hidden rounded-md">
          <div className="flex items-center justify-between border-b border-line px-5 py-4">
            <div>
              <h2 className="font-semibold">Pending Approvals</h2>
              <p className="mt-1 text-sm text-slate-500">{pendingApprovals.length} awaiting a reviewer decision.</p>
            </div>
            <Link href="/mcp-governance/approvals" className="focus-ring inline-flex items-center text-sm font-semibold text-accent hover:text-teal-700">
              <ShieldCheck className="mr-1" size={15} aria-hidden="true" />
              Open queue
            </Link>
          </div>
          {pendingApprovals.length === 0 ? (
            <div className="p-6">
              <EmptyState title="No pending approvals" body="High-risk agent runs will appear here for human review." />
            </div>
          ) : (
            <ul className="divide-y divide-line">
              {pendingApprovals.slice(0, 5).map((approval) => (
                <li key={approval.id} className="p-4">
                  <div className="flex items-center justify-between gap-2">
                    <Link href={`/mcp-governance/runs/${approval.agent_run_id}`} className="text-sm font-semibold text-ink hover:text-accent">
                      {approval.campaign_name ?? `Campaign ${approval.campaign_id}`}
                    </Link>
                    <RiskBadge value={approval.risk_level} />
                  </div>
                  <p className="mt-2 line-clamp-2 text-sm text-slate-600">{approval.proposed_action}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="panel overflow-hidden rounded-md">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div>
            <h2 className="font-semibold">Top MCP Tools</h2>
            <p className="mt-1 text-sm text-slate-500">Most-used governed tools by call volume.</p>
          </div>
          <Link href="/mcp-governance/tools" className="focus-ring inline-flex items-center text-sm font-semibold text-accent hover:text-teal-700">
            <Wrench className="mr-1" size={15} aria-hidden="true" />
            View registry
            <ArrowRight className="ml-1" size={14} aria-hidden="true" />
          </Link>
        </div>
        {topTools.length === 0 ? (
          <div className="p-6">
            <EmptyState title="No tool calls recorded yet" body="Tool usage will populate once agent runs are executed." />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-line text-sm">
              <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Tool</th>
                  <th className="px-4 py-3">Category</th>
                  <th className="px-4 py-3">Calls</th>
                  <th className="px-4 py-3">Failure rate</th>
                  <th className="px-4 py-3">Last used</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line bg-white">
                {topTools.map((tool) => (
                  <tr key={tool.name} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-medium text-ink">{tool.name}</td>
                    <td className="px-4 py-3 text-slate-600">{tool.category}</td>
                    <td className="px-4 py-3">{formatNumber(tool.call_count)}</td>
                    <td className="px-4 py-3">{formatPercent(tool.failure_rate)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-500">
                      {tool.last_used_at ? formatDateTime(tool.last_used_at) : "Never"}
                    </td>
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
