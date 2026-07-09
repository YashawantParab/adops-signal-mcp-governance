"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Bot, ClipboardCheck, FileText, History } from "lucide-react";
import { Suspense, useEffect, useMemo, useState } from "react";

import { AgentResult } from "@/components/AgentResult";
import { ClientSafeBrief } from "@/components/ClientSafeBrief";
import { PageHeader } from "@/components/PageHeader";
import { ErrorState, LoadingState } from "@/components/StateViews";
import { WorkflowBar } from "@/components/WorkflowBar";
import { api, formatPercent } from "@/lib/api";
import type { AgentDiagnosis, CampaignSummary, ClientSummaryResponse } from "@/types";

const queryPresets = [
  "Why is this campaign underdelivering?",
  "Which targeting rule is restricting delivery?",
  "Is a VAST or creative issue affecting delivery?",
  "Can this campaign still hit its goal?"
];

function AgentWorkspace() {
  const searchParams = useSearchParams();
  const initialCampaignId = Number(searchParams.get("campaignId"));
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [campaignId, setCampaignId] = useState<number | "">("");
  const [query, setQuery] = useState("Why is this campaign underdelivering?");
  const [result, setResult] = useState<AgentDiagnosis | null>(null);
  const [clientSummary, setClientSummary] = useState<ClientSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [generatingSummary, setGeneratingSummary] = useState(false);
  const [error, setError] = useState<unknown>(null);

  function loadCampaigns() {
    setLoading(true);
    setError(null);
    api
      .campaigns()
      .then((items) => {
        setCampaigns(items);
        const selected = items.some((item) => item.id === initialCampaignId) ? initialCampaignId : items[0]?.id;
        setCampaignId(selected || "");
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(loadCampaigns, [initialCampaignId]);

  const selectedCampaign = useMemo(() => campaigns.find((campaign) => campaign.id === campaignId), [campaignId, campaigns]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!campaignId) return;
    setRunning(true);
    setError(null);
    try {
      const diagnosis = await api.diagnose(Number(campaignId), query);
      setResult(diagnosis);
      setClientSummary(null);
    } catch (err) {
      setError(err);
    } finally {
      setRunning(false);
    }
  }

  async function generateSummary() {
    if (!result) return;
    setGeneratingSummary(true);
    setError(null);
    try {
      const response = await api.clientSummary(result.campaign_id, result.diagnosis);
      setClientSummary(response);
    } catch (err) {
      setError(err);
    } finally {
      setGeneratingSummary(false);
    }
  }

  if (loading) return <LoadingState label="Loading agent workspace" />;

  return (
    <>
      <PageHeader
        title="Campaign Investigation"
        subtitle="Review bounded platform evidence, establish the likely root cause, and prepare an operator-controlled resolution."
      />
      <WorkflowBar currentStep={2} />
      {error ? <div className="mb-5"><ErrorState error={error} onRetry={campaigns.length ? undefined : loadCampaigns} /></div> : null}

      <form onSubmit={submit} className="panel mb-6 rounded-md p-5">
        <div className="grid gap-4 lg:grid-cols-[300px_1fr_auto] lg:items-end">
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Campaign</span>
            <select
              value={campaignId}
              onChange={(event) => {
                setCampaignId(Number(event.target.value));
                setResult(null);
                setClientSummary(null);
              }}
              className="focus-ring mt-2 w-full rounded-md border border-line bg-white px-3 py-2 text-sm"
            >
              {campaigns.map((campaign) => (
                <option key={campaign.id} value={campaign.id}>
                  {campaign.id} - {campaign.campaign_name}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Question</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="focus-ring mt-2 w-full rounded-md border border-line px-3 py-2 text-sm"
              placeholder="Which targeting rule is killing delivery?"
            />
          </label>
          <button
            type="submit"
            className="focus-ring inline-flex items-center justify-center rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-60"
            disabled={!campaignId || running}
          >
            <Bot className="mr-2" size={16} aria-hidden="true" />
            {running ? "Running" : "Diagnose"}
          </button>
        </div>
        {selectedCampaign ? (
          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line pt-4 text-sm">
            <span className="font-medium text-slate-700">{selectedCampaign.risk_level} risk</span>
            <span className="text-slate-500">{formatPercent(selectedCampaign.pacing_percentage)} pacing</span>
            <span className="text-slate-500">{selectedCampaign.main_issue}</span>
            <Link href={`/campaigns/${selectedCampaign.id}`} className="font-semibold text-accent hover:text-teal-700">
              Review campaign data
            </Link>
          </div>
        ) : null}
        <div className="mt-4 flex flex-wrap gap-2">
          {queryPresets.map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => setQuery(preset)}
              className={`focus-ring rounded-md border px-3 py-1.5 text-xs font-medium ${
                query === preset ? "border-ink bg-ink text-white" : "border-line bg-white text-slate-600 hover:bg-slate-50"
              }`}
            >
              {preset}
            </button>
          ))}
        </div>
      </form>

      {running ? <LoadingState label="Collecting campaign evidence and ranking root causes" /> : null}

      {result && !running ? (
        <>
          <AgentResult result={result} />
          <section className="mt-4 border border-line bg-white p-5 shadow-panel">
            <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
              <div>
                <p className="text-xs font-semibold uppercase text-accent">Resolution handoff</p>
                <h2 className="mt-1 text-lg font-semibold">Move the investigation into controlled action</h2>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                  Prepare external communication, record the operational decision, and retain the evidence trace for review.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={generateSummary}
                  disabled={generatingSummary}
                  className="focus-ring inline-flex items-center rounded-md border border-line px-3 py-2 text-sm font-semibold hover:bg-slate-50 disabled:opacity-60"
                >
                  <FileText className="mr-2" size={16} aria-hidden="true" />
                  {generatingSummary ? "Generating" : "Create client brief"}
                </button>
                <Link
                  href={`/recommendations?campaignId=${result.campaign_id}`}
                  className="focus-ring inline-flex items-center rounded-md bg-ink px-3 py-2 text-sm font-semibold text-white hover:bg-slate-700"
                >
                  <ClipboardCheck className="mr-2" size={16} aria-hidden="true" />
                  Review decisions
                  <ArrowRight className="ml-2" size={14} aria-hidden="true" />
                </Link>
                <Link
                  href={`/audit-logs?campaignId=${result.campaign_id}`}
                  className="focus-ring inline-flex h-10 w-10 items-center justify-center rounded-md border border-line text-slate-600 hover:bg-slate-50"
                  aria-label="Open investigation audit history"
                  title="Open audit history"
                >
                  <History size={16} aria-hidden="true" />
                </Link>
              </div>
            </div>
            {clientSummary ? (
              <div className="mt-5">
                <ClientSafeBrief summary={clientSummary.summary} omittedInternalDetails={clientSummary.omitted_internal_details} />
              </div>
            ) : null}
          </section>
        </>
      ) : null}
    </>
  );
}

export default function AgentPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading agent workspace" />}>
      <AgentWorkspace />
    </Suspense>
  );
}
