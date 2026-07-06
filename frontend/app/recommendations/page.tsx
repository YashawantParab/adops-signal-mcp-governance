"use client";

import Link from "next/link";
import { Check, History, ShieldCheck, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { PageHeader } from "@/components/PageHeader";
import { RiskBadge } from "@/components/RiskBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";
import { WorkflowBar } from "@/components/WorkflowBar";
import { api } from "@/lib/api";
import type { Recommendation } from "@/types";

const DECISION_ROLES = ["admin", "adops_manager"];

function RecommendationWorkspace() {
  const { user } = useAuth();
  const canDecide = DECISION_ROLES.includes(user.role);
  const searchParams = useSearchParams();
  const initialCampaignId = searchParams.get("campaignId") ?? "All";
  const [items, setItems] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [campaignFilter, setCampaignFilter] = useState(initialCampaignId);
  const [statusFilter, setStatusFilter] = useState("pending");
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    api
      .recommendations()
      .then(setItems)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const campaignIds = useMemo(() => Array.from(new Set(items.map((item) => item.campaign_id))).sort(), [items]);
  const visibleItems = useMemo(
    () =>
      items.filter(
        (item) =>
          (campaignFilter === "All" || item.campaign_id === Number(campaignFilter)) &&
          (statusFilter === "All" || item.status === statusFilter)
      ),
    [campaignFilter, items, statusFilter]
  );
  const pendingCount = items.filter((item) => item.status === "pending").length;

  async function update(id: number, action: "approve" | "reject") {
    const reason = reasons[id]?.trim() ?? "";
    if (reason.length < 3) {
      setError("Record a short decision rationale before approving or rejecting an action.");
      return;
    }
    setUpdatingId(id);
    setError(null);
    setNotice(null);
    try {
      const updated =
        action === "approve" ? await api.approveRecommendation(id, reason) : await api.rejectRecommendation(id, reason);
      setItems((current) => current.map((item) => (item.id === id ? updated : item)));
      setNotice(`Recommendation ${id} was ${updated.status}. The rationale is now part of the governance record.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setUpdatingId(null);
    }
  }

  if (loading) return <LoadingState label="Loading decision queue" />;

  return (
    <>
      <PageHeader
        title="Decision Queue"
        subtitle="Authorize or reject proposed campaign changes with a recorded rationale and accountable reviewer."
      />
      <WorkflowBar currentStep={3} />
      {error ? (
        <div className="mb-5">
          <ErrorState message={error} />
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
            <p className="font-semibold">{pendingCount} decisions awaiting review</p>
            <p className="mt-1 text-sm text-slate-500">No campaign setting is changed automatically.</p>
          </div>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <label>
            <span className="sr-only">Campaign filter</span>
            <select
              value={campaignFilter}
              onChange={(event) => setCampaignFilter(event.target.value)}
              className="focus-ring w-full rounded-md border border-line bg-white px-3 py-2 text-sm sm:w-44"
            >
              <option value="All">All campaigns</option>
              {campaignIds.map((campaignId) => (
                <option key={campaignId} value={campaignId}>
                  Campaign {campaignId}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="sr-only">Decision status filter</span>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              className="focus-ring w-full rounded-md border border-line bg-white px-3 py-2 text-sm sm:w-40"
            >
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
              <option value="All">All statuses</option>
            </select>
          </label>
        </div>
      </section>

      {visibleItems.length === 0 ? (
        <EmptyState title="No decisions in this view" body="Change the campaign or status filter, or run a new investigation." />
      ) : (
        <section className="panel overflow-hidden">
          {visibleItems.map((item) => (
            <article key={item.id} className="border-b border-line p-5 last:border-b-0">
              <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Link href={`/campaigns/${item.campaign_id}`} className="text-xs font-semibold uppercase text-accent">
                      Campaign {item.campaign_id}
                    </Link>
                    <RiskBadge value={item.status} />
                    <span className="text-xs text-slate-400">Recommendation {item.id}</span>
                  </div>
                  <h2 className="mt-2 text-lg font-semibold">{item.title}</h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-700">{item.description}</p>
                  <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
                    <span className="text-slate-500">Expected impact</span>
                    <RiskBadge value={item.expected_impact} />
                    <span className="text-slate-500">Execution risk</span>
                    <RiskBadge value={item.risk_level} />
                  </div>
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
                        onClick={() => update(item.id, "approve")}
                        disabled={updatingId === item.id || (reasons[item.id]?.trim().length ?? 0) < 3}
                        className="focus-ring inline-flex items-center rounded-md bg-accent px-3 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-50"
                      >
                        <Check className="mr-2" size={16} aria-hidden="true" />
                        Approve
                      </button>
                      <button
                        type="button"
                        onClick={() => update(item.id, "reject")}
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
                    <p className="mt-2 text-sm leading-6 text-slate-600">
                      Approving or rejecting requires the AdOps Manager role. Your role ({user.role.replace("_", " ")}) has
                      read-only access to this decision.
                    </p>
                  </div>
                ) : (
                  <div className="border-l-0 border-line bg-slate-50 p-4 xl:border-l">
                    <p className="text-xs font-semibold uppercase text-slate-500">Recorded decision</p>
                    <p className="mt-2 text-sm leading-6 text-slate-700">{item.decision_reason}</p>
                    <p className="mt-3 text-xs text-slate-500">
                      User {item.decided_by_user_id} · {item.decided_at ? new Date(item.decided_at).toLocaleString() : "Time unavailable"}
                    </p>
                    <Link
                      href={`/audit-logs?campaignId=${item.campaign_id}`}
                      className="mt-3 inline-flex items-center text-sm font-semibold text-accent hover:text-teal-700"
                    >
                      <History className="mr-2" size={15} aria-hidden="true" />
                      Open audit record
                    </Link>
                  </div>
                )}
              </div>
            </article>
          ))}
        </section>
      )}
    </>
  );
}

export default function RecommendationsPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading decision queue" />}>
      <RecommendationWorkspace />
    </Suspense>
  );
}
