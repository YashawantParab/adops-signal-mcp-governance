"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, History, ShieldAlert, ShieldCheck } from "lucide-react";

import { formatDateTime, formatReviewer } from "@/lib/api";
import type { MCPAgentRunDetail, MCPAgentRunResponse, MCPToolDescriptor } from "@/types";

import { RiskBadge } from "./RiskBadge";

interface CampaignHealthOutput {
  risk_level: string;
  pacing_percentage: number;
  creative_status: string;
  vast_error_count: number;
  main_suspected_issue: string;
}

interface PacingOutput {
  found: boolean;
  pacing_percentage: number | null;
  risk_level: string | null;
  delta_percentage_points: number | null;
  snapshot_count: number;
}

interface VastOutput {
  creative_count: number;
  rejected_count: number;
  vast_error_count: number;
  valid: boolean;
  suggested_fix: string;
}

interface BrandSafetyFinding {
  type: string;
  severity: string;
  message: string;
  evidence: Record<string, unknown>;
}

interface BrandSafetyOutput {
  findings: BrandSafetyFinding[];
  finding_count: number;
}

interface PolicyMatch {
  source: string;
  title: string;
  score: number;
  matched_keywords: string[];
}

interface PolicySearchOutput {
  matches: PolicyMatch[];
}

function toolOutput<T>(detail: MCPAgentRunDetail | null, toolName: string): T | null {
  const call = detail?.tool_calls.find((item) => item.tool_name === toolName);
  return call ? (call.output_json as T) : null;
}

function timelineSummary(result: MCPAgentRunResponse, toolName: string): string | null {
  return result.tool_timeline.find((item) => item.tool_name === toolName)?.summary ?? null;
}

function formatEvidence(evidence: Record<string, unknown>): string {
  return Object.entries(evidence)
    .map(([key, value]) => `${key.replaceAll("_", " ")}: ${Array.isArray(value) ? value.join(", ") : String(value)}`)
    .join(" · ");
}

function SectionShell({
  eyebrow,
  title,
  children,
  right
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
  right?: React.ReactNode;
}) {
  return (
    <section className="panel rounded-md p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase text-accent">{eyebrow}</p>
          <h3 className="mt-1 text-base font-semibold">{title}</h3>
        </div>
        {right}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Fallback({ text }: { text: string | null }) {
  return (
    <p className="text-sm text-slate-500">
      {text ?? "This signal was not returned for this run."}
    </p>
  );
}

export function MCPAgentRunResult({
  result,
  detail,
  toolDescriptions
}: {
  result: MCPAgentRunResponse;
  detail: MCPAgentRunDetail | null;
  toolDescriptions: Record<string, MCPToolDescriptor>;
}) {
  const health = toolOutput<CampaignHealthOutput>(detail, "get_campaign_health");
  const pacing = toolOutput<PacingOutput>(detail, "get_campaign_pacing");
  const vast = toolOutput<VastOutput>(detail, "get_vast_validation_summary");
  const brand = toolOutput<BrandSafetyOutput>(detail, "get_brand_safety_findings");
  const policySearch = toolOutput<PolicySearchOutput>(detail, "search_policy_context");
  const policyCheck = detail?.policy_checks[0] ?? null;

  return (
    <div className="space-y-4">
      {/* 1. Agent Summary */}
      <section className="panel rounded-md p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase text-accent">Agent Summary</p>
            <h2 className="mt-1 text-lg font-semibold">
              Campaign {result.campaign_id}
              {detail?.campaign_name ? ` · ${detail.campaign_name}` : ""}
            </h2>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-700">{result.summary}</p>
            {detail?.user_query ? <p className="mt-2 text-xs text-slate-500">Query: &ldquo;{detail.user_query}&rdquo;</p> : null}
          </div>
          <div className="flex flex-col items-end gap-2">
            <RiskBadge value={result.status} />
            <RiskBadge value={result.risk_level} />
          </div>
        </div>
        <p className="mt-4 text-xs text-slate-500">
          Agent run #{result.agent_run_id}
          {detail?.created_at ? ` · ${formatDateTime(detail.created_at)}` : ""}
        </p>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* 2. Campaign Health */}
        <SectionShell eyebrow="Signal" title="Campaign Health" right={health ? <RiskBadge value={health.risk_level} /> : undefined}>
          {health ? (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-xs font-medium uppercase text-slate-500">Pacing</p>
                  <p className="mt-1 text-xl font-semibold text-ink">{health.pacing_percentage}%</p>
                  {pacing?.found && pacing.delta_percentage_points !== null ? (
                    <p className="mt-1 text-xs text-slate-500">
                      {pacing.delta_percentage_points >= 0 ? "+" : ""}
                      {pacing.delta_percentage_points} pts vs prior snapshot · {pacing.snapshot_count} snapshots
                    </p>
                  ) : null}
                </div>
                <div>
                  <p className="text-xs font-medium uppercase text-slate-500">Creative status</p>
                  <p className="mt-1 font-medium text-ink">{health.creative_status}</p>
                  <p className="mt-1 text-xs text-slate-500">{health.vast_error_count} persisted VAST error(s)</p>
                </div>
              </div>
              <div className="rounded-md border border-line bg-slate-50 p-3">
                <p className="text-xs font-semibold uppercase text-slate-500">Main suspected issue</p>
                <p className="mt-1 text-slate-700">{health.main_suspected_issue}</p>
              </div>
            </div>
          ) : (
            <Fallback text={timelineSummary(result, "get_campaign_health")} />
          )}
        </SectionShell>

        {/* 3. VAST Findings */}
        <SectionShell eyebrow="Signal" title="VAST Findings" right={vast ? <RiskBadge value={vast.valid ? "valid" : "needs_review"} /> : undefined}>
          {vast ? (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <p className="text-xs font-medium uppercase text-slate-500">Creatives</p>
                  <p className="mt-1 text-xl font-semibold text-ink">{vast.creative_count}</p>
                </div>
                <div>
                  <p className="text-xs font-medium uppercase text-slate-500">Rejected</p>
                  <p className="mt-1 text-xl font-semibold text-ink">{vast.rejected_count}</p>
                </div>
                <div>
                  <p className="text-xs font-medium uppercase text-slate-500">VAST errors</p>
                  <p className="mt-1 text-xl font-semibold text-ink">{vast.vast_error_count}</p>
                </div>
              </div>
              <p className="rounded-md border border-line bg-slate-50 p-3 leading-6 text-slate-700">{vast.suggested_fix}</p>
            </div>
          ) : (
            <Fallback text={timelineSummary(result, "get_vast_validation_summary")} />
          )}
        </SectionShell>
      </div>

      {/* 4. Brand Safety Findings */}
      <SectionShell
        eyebrow="Signal"
        title="Brand Safety Findings"
        right={brand ? <span className="text-xs font-medium text-slate-500">{brand.finding_count} finding(s)</span> : undefined}
      >
        {brand ? (
          brand.findings.length ? (
            <div className="space-y-3">
              {brand.findings.map((finding, index) => (
                <div key={`${finding.type}-${index}`} className="rounded-md border border-line p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-medium">{finding.type.replaceAll("_", " ")}</p>
                    <RiskBadge value={finding.severity} />
                  </div>
                  <p className="mt-2 text-sm leading-5 text-slate-600">{finding.message}</p>
                  {Object.keys(finding.evidence ?? {}).length ? (
                    <p className="mt-2 text-xs text-slate-400">{formatEvidence(finding.evidence)}</p>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">No brand-safety findings identified for this campaign.</p>
          )
        ) : (
          <Fallback text={timelineSummary(result, "get_brand_safety_findings")} />
        )}
      </SectionShell>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* 5. Policy Context Used */}
        <SectionShell
          eyebrow="Governance"
          title="Policy Context Used"
          right={policyCheck ? <RiskBadge value={policyCheck.result} /> : undefined}
        >
          {policyCheck ? (
            <div className="space-y-3 text-sm">
              <div className="rounded-md border border-line bg-slate-50 p-3">
                <p className="text-xs font-semibold uppercase text-slate-500">Policy matched</p>
                <p className="mt-1 font-medium text-ink">{policyCheck.policy_name}</p>
                <p className="mt-1 text-xs text-slate-500">{policyCheck.citation}</p>
                {policyCheck.matched_rules.length ? (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {policyCheck.matched_rules.map((rule) => (
                      <span key={String(rule)} className="rounded-md border border-line bg-white px-2 py-1 text-xs">
                        {String(rule)}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
              {policySearch?.matches.length ? (
                <div className="space-y-2">
                  <p className="text-xs font-semibold uppercase text-slate-500">Other policy matches</p>
                  {policySearch.matches.map((match) => (
                    <div key={match.source} className="rounded-md border border-line p-2 text-xs">
                      <p className="font-medium text-slate-700">{match.title}</p>
                      <p className="mt-1 text-slate-400">{match.source} · score {match.score}</p>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : (
            <Fallback text={timelineSummary(result, "search_policy_context")} />
          )}
        </SectionShell>

        {/* 6. Risk Score */}
        <SectionShell eyebrow="Governance" title="Risk Score" right={<RiskBadge value={result.risk_level} />}>
          <div className="flex items-end gap-4">
            <p className="text-4xl font-semibold text-ink">{result.risk_score}</p>
            <p className="pb-1 text-sm text-slate-500">/ 100</p>
          </div>
          <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className={`h-full rounded-full ${
                result.risk_level === "CRITICAL"
                  ? "bg-red-600"
                  : result.risk_level === "HIGH"
                    ? "bg-red-400"
                    : result.risk_level === "MEDIUM"
                      ? "bg-amber-400"
                      : "bg-emerald-500"
              }`}
              style={{ width: `${Math.min(Math.max(result.risk_score, 0), 100)}%` }}
            />
          </div>
        </SectionShell>
      </div>

      {/* 7. Approval Required */}
      <section
        className={`panel rounded-md p-5 ${
          result.blocked ? "border-red-200 bg-red-50" : result.approval_required ? "border-amber-200 bg-amber-50" : ""
        }`}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase text-accent">Governance</p>
            <h3 className="mt-1 flex items-center gap-2 text-base font-semibold">
              {result.blocked ? (
                <>
                  <ShieldAlert size={18} className="text-red-700" aria-hidden="true" /> Blocked - human review required
                </>
              ) : result.approval_required ? (
                <>
                  <AlertTriangle size={18} className="text-amber-700" aria-hidden="true" /> Approval Required
                </>
              ) : (
                <>
                  <ShieldCheck size={18} className="text-emerald-700" aria-hidden="true" /> No Approval Required
                </>
              )}
            </h3>
          </div>
        </div>
        <p className="mt-3 text-sm leading-6 text-slate-700">
          The agent only recommends action and creates approval or block records - it never executes campaign, budget, or pacing
          changes.
        </p>
        {detail?.blocked_actions.length ? (
          <div className="mt-4 space-y-2">
            {detail.blocked_actions.map((action) => (
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
        ) : null}
        {detail?.approval_requests.length ? (
          <div className="mt-4 space-y-2">
            {detail.approval_requests.map((approval) => (
              <div key={approval.id} className="rounded-md border border-amber-200 bg-white p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-medium">{approval.proposed_action}</p>
                  <RiskBadge value={approval.status} />
                </div>
                <p className="mt-2 text-slate-600">{approval.rationale}</p>
                <p className="mt-2 text-xs text-slate-400">
                  {approval.status === "pending"
                    ? "Awaiting authorized reviewer"
                    : `${formatReviewer(approval.reviewer_name, null, approval.reviewer_id)} · ${
                        approval.reviewed_at ? formatDateTime(approval.reviewed_at) : "Time unavailable"
                      }`}
                </p>
              </div>
            ))}
          </div>
        ) : null}
      </section>

      {/* 8. MCP Tool Timeline */}
      <section className="panel rounded-md p-5">
        <p className="text-xs font-semibold uppercase text-accent">Governance</p>
        <h3 className="mt-1 text-base font-semibold">MCP Tool Timeline</h3>
        <ol className="mt-4 space-y-2">
          {result.tool_timeline.map((entry) => (
            <li key={entry.step} className="flex items-start gap-3 rounded-md border border-line p-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-line text-xs font-semibold text-slate-600">
                {entry.step}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    title={toolDescriptions[entry.tool_name]?.description ?? entry.tool_name}
                    className="rounded-md border border-line bg-slate-50 px-2 py-1 text-xs font-medium text-slate-700"
                  >
                    {entry.tool_name}
                  </span>
                  <RiskBadge value={entry.status} />
                  <span className="text-xs text-slate-400">{entry.latency_ms} ms</span>
                </div>
                <p className="mt-2 text-sm leading-5 text-slate-700">{entry.summary}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* 9. Final Recommendation */}
      <section className="panel rounded-md p-5">
        <p className="text-xs font-semibold uppercase text-accent">Outcome</p>
        <h3 className="mt-1 text-base font-semibold">Final Recommendation</h3>
        <p className="mt-3 text-sm leading-6 text-slate-700">{result.final_recommendation}</p>
      </section>

      {/* 10. Link to full run detail, where available */}
      <section className="panel flex flex-wrap items-center justify-between gap-3 rounded-md p-5">
        <div>
          <p className="text-xs font-semibold uppercase text-accent">Record</p>
          <p className="mt-1 text-sm text-slate-600">
            Agent run #{result.agent_run_id} is retained in the governance audit trail for campaign {result.campaign_id}.
          </p>
        </div>
        <Link
          href={`/audit-logs?campaignId=${result.campaign_id}`}
          className="focus-ring inline-flex items-center rounded-md border border-line px-3 py-2 text-sm font-semibold hover:bg-slate-50"
        >
          <History className="mr-2" size={16} aria-hidden="true" />
          Open governance audit trail
          <ArrowRight className="ml-2" size={14} aria-hidden="true" />
        </Link>
      </section>
    </div>
  );
}
