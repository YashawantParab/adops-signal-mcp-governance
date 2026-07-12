"use client";

import Link from "next/link";
import { Check, ShieldCheck, X } from "lucide-react";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { PageHeader } from "@/components/PageHeader";
import { RiskBadge } from "@/components/RiskBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";
import { api, DEMO_VIEWER_ROLE, formatDateTime, formatReviewer } from "@/lib/api";
import type { MCPApprovalRequest } from "@/types";

const DECISION_ROLES = ["admin", "adops_manager"];

interface PolicyRef {
  loading: boolean;
  title: string | null;
  citation: string | null;
}

export default function MCPGovernanceApprovalsPage() {
  const { user } = useAuth();
  const canDecide = !!user && DECISION_ROLES.includes(user.role);

  const [items, setItems] = useState<MCPApprovalRequest[]>([]);
  const [statusFilter, setStatusFilter] = useState("pending");
  const [loading, setLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [policyRefs, setPolicyRefs] = useState<Record<number, PolicyRef>>({});

  function load() {
    setLoading(true);
    setError(null);
    api
      .mcpApprovals()
      .then(setItems)
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  useEffect(() => {
    const pending = items.filter((item) => item.status === "pending" && !(item.agent_run_id in policyRefs));
    if (!pending.length) return;
    for (const approval of pending) {
      setPolicyRefs((current) => ({ ...current, [approval.agent_run_id]: { loading: true, title: null, citation: null } }));
      api
        .mcpRunDetail(approval.agent_run_id)
        .then((detail) => {
          const check = detail.policy_checks[0];
          setPolicyRefs((current) => ({
            ...current,
            [approval.agent_run_id]: { loading: false, title: check?.policy_name ?? null, citation: check?.citation ?? null }
          }));
        })
        .catch(() => {
          setPolicyRefs((current) => ({ ...current, [approval.agent_run_id]: { loading: false, title: null, citation: null } }));
        });
    }
    // Intentionally re-runs only when the visible item set changes, not on every policyRefs update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  const visibleItems = items.filter((item) => statusFilter === "All" || item.status === statusFilter);
  const pendingCount = items.filter((item) => item.status === "pending").length;

  async function decide(id: number, action: "approve" | "reject") {
    const reason = reasons[id]?.trim() ?? "";
    if (reason.length < 3) {
      setError("Record a short decision rationale before approving or rejecting an action.");
      return;
    }
    setUpdatingId(id);
    setError(null);
    setNotice(null);
    try {
      const updated = action === "approve" ? await api.approveMcpApproval(id, reason) : await api.rejectMcpApproval(id, reason);
      setItems((current) => current.map((item) => (item.id === id ? updated : item)));
      setNotice(`Approval ${id} was ${updated.status}. The decision is recorded in the governance record.`);
    } catch (err) {
      setError(err);
    } finally {
      setUpdatingId(null);
    }
  }

  if (loading) return <LoadingState label="Loading MCP decision queue" />;

  return (
    <>
      <PageHeader
        title="MCP Decision Queue"
        subtitle="Authorize or reject high-risk agent-proposed actions. Approving here never executes a campaign change - it records a governance decision."
      />
      {error ? (
        <div className="mb-5">
          <ErrorState error={error} onRetry={items.length ? undefined : load} />
        </div>
      ) : null}
      {notice ? (
        <div className="mb-5 border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">{notice}</div>
      ) : null}

      <section className="panel mb-5 flex flex-col justify-between gap-4 p-4 lg:flex-row lg:items-center">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-amber-50 text-amber-700">
            <ShieldCheck size={19} aria-hidden="true" />
          </div>
          <div>
            <p className="font-semibold">{pendingCount} approvals awaiting review</p>
            <p className="mt-1 text-sm text-slate-500">No campaign, budget, or pacing setting is changed automatically.</p>
          </div>
        </div>
        <label>
          <span className="sr-only">Decision status filter</span>
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="focus-ring w-full rounded-md border border-line bg-white px-3 py-2 text-sm sm:w-44"
          >
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="All">All statuses</option>
          </select>
        </label>
      </section>

      {visibleItems.length === 0 ? (
        <EmptyState title="No approvals in this view" body="Change the status filter, or run a new investigation that triggers a HIGH risk finding." />
      ) : (
        <section className="panel overflow-hidden">
          {visibleItems.map((item) => {
            const policyRef = policyRefs[item.agent_run_id];
            return (
              <article key={item.id} className="border-b border-line p-5 last:border-b-0">
                <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Link href={`/mcp-governance/runs/${item.agent_run_id}`} className="text-xs font-semibold uppercase text-accent">
                        Run #{item.agent_run_id}
                      </Link>
                      <RiskBadge value={item.status} />
                      <RiskBadge value={item.risk_level} />
                      <span className="text-xs text-slate-400">Score {item.risk_score}</span>
                    </div>
                    <Link href={`/campaigns/${item.campaign_id}`} className="mt-2 block text-lg font-semibold hover:text-accent">
                      {item.campaign_name ?? `Campaign ${item.campaign_id}`}
                    </Link>
                    <p className="mt-1 text-xs font-semibold uppercase text-slate-500">Proposed action</p>
                    <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-700">{item.proposed_action}</p>
                    <p className="mt-3 text-xs font-semibold uppercase text-slate-500">Risk rationale</p>
                    <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-700">{item.rationale}</p>
                    <p className="mt-3 text-xs font-semibold uppercase text-slate-500">Policy reference</p>
                    <p className="mt-1 text-sm text-slate-600">
                      {policyRef?.loading
                        ? "Loading policy reference..."
                        : policyRef?.title
                          ? `${policyRef.title} (${policyRef.citation})`
                          : "No local policy document matched this run."}
                    </p>
                  </div>

                  {item.status === "pending" && canDecide ? (
                    <div className="border-l-0 border-line xl:border-l xl:pl-5">
                      <label className="block">
                        <span className="text-sm font-medium text-slate-700">Decision rationale</span>
                        <textarea
                          value={reasons[item.id] ?? ""}
                          onChange={(event) => setReasons((current) => ({ ...current, [item.id]: event.target.value }))}
                          rows={3}
                          className="focus-ring mt-2 w-full resize-none rounded-md border border-line px-3 py-2 text-sm"
                          placeholder="Evidence checked, expected outcome, and operational constraint"
                        />
                      </label>
                      <div className="mt-3 flex gap-2">
                        <button
                          type="button"
                          onClick={() => decide(item.id, "approve")}
                          disabled={updatingId === item.id || (reasons[item.id]?.trim().length ?? 0) < 3}
                          className="focus-ring inline-flex items-center rounded-md bg-accent px-3 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-50"
                        >
                          <Check className="mr-2" size={16} aria-hidden="true" />
                          Approve
                        </button>
                        <button
                          type="button"
                          onClick={() => decide(item.id, "reject")}
                          disabled={updatingId === item.id || (reasons[item.id]?.trim().length ?? 0) < 3}
                          className="focus-ring inline-flex items-center rounded-md border border-line px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                        >
                          <X className="mr-2" size={16} aria-hidden="true" />
                          Reject
                        </button>
                      </div>
                    </div>
                  ) : item.status === "pending" ? (
                    <div className="border-l-0 border-line bg-slate-50 p-4 xl:border-l">
                      <p className="text-xs font-semibold uppercase text-slate-500">Awaiting authorized review</p>
                      {user?.role === DEMO_VIEWER_ROLE ? (
                        <p className="mt-2 text-sm leading-6 text-slate-600">
                          Public demo is read-only.{" "}
                          <Link href="/" className="font-semibold text-accent hover:text-teal-700">
                            Use the full demo login
                          </Link>{" "}
                          for approval actions.
                        </p>
                      ) : (
                        <p className="mt-2 text-sm leading-6 text-slate-600">
                          Approving or rejecting requires the AdOps Manager role. Your role ({(user?.role ?? "unknown").replace("_", " ")}
                          ) has read-only access to this decision.
                        </p>
                      )}
                    </div>
                  ) : (
                    <div className="border-l-0 border-line bg-slate-50 p-4 xl:border-l">
                      <p className="text-xs font-semibold uppercase text-slate-500">Recorded decision</p>
                      <p className="mt-2 text-sm leading-6 text-slate-700">{item.rationale}</p>
                      <p className="mt-3 text-xs text-slate-500">
                        {formatReviewer(item.reviewer_name, null, item.reviewer_id)} ·{" "}
                        {item.reviewed_at ? formatDateTime(item.reviewed_at) : "Time unavailable"}
                      </p>
                    </div>
                  )}
                </div>
              </article>
            );
          })}
        </section>
      )}
    </>
  );
}
