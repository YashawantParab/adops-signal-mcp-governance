"use client";

import Link from "next/link";
import { Bot, FileText } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AgentResult } from "@/components/AgentResult";
import { PageHeader } from "@/components/PageHeader";
import { PacingChart } from "@/components/PacingChart";
import { RiskBadge } from "@/components/RiskBadge";
import { ErrorState, LoadingState } from "@/components/StateViews";
import { StatCard } from "@/components/StatCard";
import { WorkflowBar } from "@/components/WorkflowBar";
import { api, formatNumber, formatPercent } from "@/lib/api";
import type { AgentDiagnosis, CampaignDetail } from "@/types";

export default function CampaignDetailPage() {
  const params = useParams<{ id: string }>();
  const campaignId = Number(params.id);
  const [campaign, setCampaign] = useState<CampaignDetail | null>(null);
  const [diagnosis, setDiagnosis] = useState<AgentDiagnosis | null>(null);
  const [clientSummary, setClientSummary] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [diagnosing, setDiagnosing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .campaign(campaignId)
      .then(setCampaign)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [campaignId]);

  async function runDiagnosis() {
    setDiagnosing(true);
    setClientSummary(null);
    try {
      const result = await api.diagnose(campaignId, "Why is this campaign underdelivering?");
      setDiagnosis(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Diagnosis failed");
    } finally {
      setDiagnosing(false);
    }
  }

  async function generateSummary() {
    if (!diagnosis) return;
    const response = await api.clientSummary(campaignId, diagnosis.diagnosis);
    setClientSummary(response.summary);
  }

  if (loading) return <LoadingState label="Loading campaign detail" />;
  if (error) return <ErrorState message={error} />;
  if (!campaign) return <ErrorState message="Campaign not found" />;

  return (
    <>
      <PageHeader title={campaign.campaign_name} subtitle={`${campaign.advertiser_name} - ${campaign.campaign_type} - ID ${campaign.id}`} />
      <WorkflowBar currentStep={2} />

      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Pacing" value={formatPercent(campaign.health.pacing_percentage)} hint={campaign.health.main_suspected_issue} />
        <StatCard label="Goal" value={formatNumber(campaign.goal_impressions)} hint={`${formatNumber(campaign.delivered_impressions)} delivered`} />
        <StatCard label="Eligible supply" value={formatPercent(campaign.health.inventory.eligible_inventory_percentage)} hint={`${campaign.health.inventory.eligible_segments} segments`} />
        <StatCard label="Bid win rate" value={formatPercent(campaign.health.bid_analysis.win_rate)} hint={`${formatPercent(campaign.health.bid_analysis.below_floor_rate)} below floor`} />
      </div>

      <div className="mb-6 grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <PacingChart history={campaign.pacing_history} />
        <section className="panel rounded-md p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold">Campaign Setup</h2>
              <p className="mt-1 text-sm text-slate-500">
                {campaign.start_date} to {campaign.end_date}
              </p>
            </div>
            <RiskBadge value={campaign.health.risk_level} />
          </div>
          <dl className="mt-5 grid gap-4 text-sm md:grid-cols-2">
            <div>
              <dt className="text-slate-500">Countries</dt>
              <dd className="font-medium">{campaign.target_countries.join(", ")}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Devices</dt>
              <dd className="font-medium">{campaign.target_devices.join(", ")}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Categories</dt>
              <dd className="font-medium">{campaign.target_content_categories.join(", ")}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Frequency cap</dt>
              <dd className="font-medium">{campaign.frequency_cap} per household/day</dd>
            </div>
            <div>
              <dt className="text-slate-500">Bid floor</dt>
              <dd className="font-medium">EUR {campaign.bid_floor}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Priority</dt>
              <dd className="font-medium">{campaign.priority_level}</dd>
            </div>
          </dl>
        </section>
      </div>

      <div className="mb-6 grid gap-4 xl:grid-cols-2">
        <section className="panel rounded-md p-5">
          <h2 className="text-base font-semibold">Creative Status</h2>
          <div className="mt-4 space-y-3">
            {campaign.creatives.map((creative) => (
              <div key={creative.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3 last:border-0 last:pb-0">
                <div>
                  <p className="font-medium">{creative.creative_name}</p>
                  <p className="text-sm text-slate-500">
                    {creative.duration_seconds}s - {creative.format}
                  </p>
                  {creative.rejection_reason ? <p className="mt-1 text-sm text-red-700">{creative.rejection_reason}</p> : null}
                </div>
                <RiskBadge value={creative.approval_status} />
              </div>
            ))}
          </div>
        </section>

        <section className="panel rounded-md p-5">
          <h2 className="text-base font-semibold">Inventory And Bids</h2>
          <dl className="mt-4 grid gap-4 text-sm md:grid-cols-2">
            <div>
              <dt className="text-slate-500">Eligible daily impressions</dt>
              <dd className="font-medium">{formatNumber(campaign.health.inventory.eligible_daily_impressions)}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Modeled supply</dt>
              <dd className="font-medium">{formatNumber(campaign.health.inventory.total_daily_impressions)}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Total bids</dt>
              <dd className="font-medium">{formatNumber(campaign.health.bid_analysis.total_bids)}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Average bid / floor</dt>
              <dd className="font-medium">
                EUR {campaign.health.bid_analysis.avg_bid_price} / EUR {campaign.health.bid_analysis.avg_floor_price}
              </dd>
            </div>
          </dl>
        </section>
      </div>

      <section className="mb-6 panel rounded-md p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">AI Diagnosis Panel</h2>
            <p className="mt-1 text-sm text-slate-500">Grounded in pacing, setup, targeting, inventory, creative, and bid evidence.</p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={runDiagnosis}
              className="focus-ring inline-flex items-center rounded-md bg-ink px-3 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-60"
              disabled={diagnosing}
            >
              <Bot className="mr-2" size={16} aria-hidden="true" />
              {diagnosing ? "Diagnosing" : "Run diagnosis"}
            </button>
            <Link
              href={`/agent?campaignId=${campaign.id}`}
              className="focus-ring inline-flex items-center rounded-md border border-line px-3 py-2 text-sm font-semibold hover:bg-slate-50"
            >
              Open agent
            </Link>
          </div>
        </div>
      </section>

      {diagnosis ? (
        <div className="mb-6">
          <AgentResult result={diagnosis} />
          <div className="mt-4 panel rounded-md p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-base font-semibold">Client-Safe Explanation</h3>
              <button
                type="button"
                onClick={generateSummary}
                className="focus-ring inline-flex items-center rounded-md border border-line px-3 py-2 text-sm font-semibold hover:bg-slate-50"
              >
                <FileText className="mr-2" size={16} aria-hidden="true" />
                Generate
              </button>
            </div>
            {clientSummary ? <p className="mt-3 text-sm leading-6 text-slate-700">{clientSummary}</p> : null}
          </div>
        </div>
      ) : null}
    </>
  );
}
