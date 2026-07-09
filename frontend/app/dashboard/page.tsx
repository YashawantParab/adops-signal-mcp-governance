"use client";

import Link from "next/link";
import { AlertTriangle, Bot, ExternalLink, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { RiskBadge } from "@/components/RiskBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";
import { StatCard } from "@/components/StatCard";
import { WorkflowBar } from "@/components/WorkflowBar";
import { api, formatCompactCurrency, formatCompactNumber, formatNumber, formatPercent } from "@/lib/api";
import type { CampaignSummary } from "@/types";

export default function DashboardPage() {
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [query, setQuery] = useState("");
  const [riskFilter, setRiskFilter] = useState("All");

  function load() {
    setLoading(true);
    setError(null);
    api
      .campaigns()
      .then(setCampaigns)
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  const stats = useMemo(() => {
    const highRisk = campaigns.filter((campaign) => campaign.risk_level === "High").length;
    const delivered = campaigns.reduce((sum, campaign) => sum + campaign.delivered_impressions, 0);
    const goal = campaigns.reduce((sum, campaign) => sum + campaign.goal_impressions, 0);
    const avgPacing = campaigns.length ? campaigns.reduce((sum, campaign) => sum + campaign.pacing_percentage, 0) / campaigns.length : 0;
    const deliveryGap = Math.max(goal - delivered, 0);
    const atRiskBudget = campaigns
      .filter((campaign) => campaign.risk_level === "High")
      .reduce((sum, campaign) => sum + campaign.budget, 0);
    return { highRisk, delivered, goal, avgPacing, deliveryGap, atRiskBudget };
  }, [campaigns]);

  const visibleCampaigns = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const riskWeight: Record<CampaignSummary["risk_level"], number> = { High: 3, Medium: 2, Low: 1, Unknown: 0 };
    return campaigns
      .filter((campaign) => riskFilter === "All" || campaign.risk_level === riskFilter)
      .filter(
        (campaign) =>
          !normalizedQuery ||
          campaign.campaign_name.toLowerCase().includes(normalizedQuery) ||
          campaign.advertiser_name?.toLowerCase().includes(normalizedQuery) ||
          String(campaign.id).includes(normalizedQuery)
      )
      .sort((left, right) => {
        return riskWeight[right.risk_level] - riskWeight[left.risk_level] || left.pacing_percentage - right.pacing_percentage;
      });
  }, [campaigns, query, riskFilter]);

  const priorityCampaign = visibleCampaigns.find((campaign) => campaign.risk_level === "High") ?? visibleCampaigns[0];

  if (loading) return <LoadingState label="Loading campaign health" />;
  if (error) return <ErrorState error={error} onRetry={load} />;

  return (
    <>
      <PageHeader
        title="Delivery Operations"
        subtitle="Prioritize campaign risk, open an evidence-backed investigation, and move recommended actions through controlled approval."
      />
      <WorkflowBar currentStep={1} />

      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Campaigns monitored" value={formatNumber(campaigns.length)} hint="Across CTV and addressable" />
        <StatCard label="High-risk queue" value={formatNumber(stats.highRisk)} hint="Requires operator decision" />
        <StatCard
          label="Delivery gap"
          value={formatCompactNumber(stats.deliveryGap)}
          hint={`Impressions short of goal · portfolio pacing ${formatPercent(stats.avgPacing)}`}
        />
        <StatCard label="Budget under review" value={formatCompactCurrency(stats.atRiskBudget)} hint="Booked media on high-risk flights" />
      </div>

      {priorityCampaign ? (
        <section className="mb-6 flex flex-col justify-between gap-4 border border-amber-200 bg-amber-50 p-4 lg:flex-row lg:items-center">
          <div className="flex min-w-0 items-start gap-3">
            <AlertTriangle className="mt-0.5 shrink-0 text-amber-700" size={19} aria-hidden="true" />
            <div>
              <p className="text-sm font-semibold text-amber-950">Next operator action</p>
              <p className="mt-1 text-sm leading-6 text-amber-900">
                Investigate {priorityCampaign.campaign_name}: {formatPercent(priorityCampaign.pacing_percentage)} pacing with{" "}
                {priorityCampaign.main_issue.toLowerCase()}.
              </p>
            </div>
          </div>
          <Link
            href={`/agent?campaignId=${priorityCampaign.id}`}
            className="focus-ring inline-flex shrink-0 items-center justify-center rounded-md bg-ink px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-700"
          >
            <Bot className="mr-2" size={16} aria-hidden="true" />
            Start investigation
          </Link>
        </section>
      ) : null}

      {campaigns.length === 0 ? (
        <EmptyState title="No campaigns found" body="Run the backend seed script to load deterministic demo data." />
      ) : (
        <div className="panel overflow-hidden rounded-md">
          <div className="flex flex-col justify-between gap-3 border-b border-line p-4 lg:flex-row lg:items-center">
            <div>
              <h2 className="font-semibold">Campaign risk queue</h2>
              <p className="mt-1 text-sm text-slate-500">{visibleCampaigns.length} campaigns match the current view</p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <label className="relative block">
                <span className="sr-only">Search campaigns</span>
                <Search className="pointer-events-none absolute left-3 top-2.5 text-slate-400" size={16} aria-hidden="true" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  className="focus-ring w-full rounded-md border border-line py-2 pl-9 pr-3 text-sm sm:w-64"
                  placeholder="Campaign, advertiser, or ID"
                />
              </label>
              <label>
                <span className="sr-only">Filter by risk</span>
                <select
                  value={riskFilter}
                  onChange={(event) => setRiskFilter(event.target.value)}
                  className="focus-ring w-full rounded-md border border-line bg-white px-3 py-2 text-sm sm:w-36"
                >
                  <option>All</option>
                  <option>High</option>
                  <option>Medium</option>
                  <option>Low</option>
                </select>
              </label>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-line text-sm">
              <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3">Campaign</th>
                  <th className="px-4 py-3">Advertiser</th>
                  <th className="hidden px-4 py-3 2xl:table-cell">Status</th>
                  <th className="hidden px-4 py-3 2xl:table-cell">Goal</th>
                  <th className="px-4 py-3">Delivered</th>
                  <th className="px-4 py-3">Pacing</th>
                  <th className="px-4 py-3">Risk</th>
                  <th className="px-4 py-3">Main issue</th>
                  <th className="px-4 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line bg-white">
                {visibleCampaigns.map((campaign) => (
                  <tr key={campaign.id} className="hover:bg-slate-50">
                    <td className="px-4 py-4">
                      <Link className="font-semibold text-ink hover:text-accent" href={`/campaigns/${campaign.id}`}>
                        {campaign.campaign_name}
                      </Link>
                      <p className="mt-1 text-xs text-slate-500">ID {campaign.id}</p>
                    </td>
                    <td className="px-4 py-4 text-slate-700">{campaign.advertiser_name}</td>
                    <td className="hidden px-4 py-4 capitalize 2xl:table-cell">{campaign.status}</td>
                    <td className="hidden px-4 py-4 2xl:table-cell">{formatNumber(campaign.goal_impressions)}</td>
                    <td className="px-4 py-4">{formatNumber(campaign.delivered_impressions)}</td>
                    <td className="whitespace-nowrap px-4 py-4">
                      <div className="min-w-28">
                        <div className="h-2 rounded bg-slate-100">
                          <div className="h-2 rounded bg-accent" style={{ width: `${Math.min(campaign.pacing_percentage, 120)}%` }} />
                        </div>
                        <span className="mt-1 block text-xs font-medium text-slate-600">{formatPercent(campaign.pacing_percentage)}</span>
                      </div>
                    </td>
                    <td className="px-4 py-4">
                      <RiskBadge value={campaign.risk_level} />
                    </td>
                    <td className="px-4 py-4 text-slate-700">{campaign.main_issue}</td>
                    <td className="px-4 py-4">
                      <div className="flex justify-end gap-2">
                        <Link
                          href={`/agent?campaignId=${campaign.id}`}
                          className="focus-ring inline-flex items-center rounded-md bg-ink px-3 py-2 text-xs font-semibold text-white hover:bg-slate-700"
                        >
                          <Bot className="mr-1" size={14} aria-hidden="true" />
                          Diagnose
                        </Link>
                        <Link
                          href={`/campaigns/${campaign.id}`}
                          className="focus-ring inline-flex items-center rounded-md border border-line px-2 py-2 text-slate-600 hover:bg-slate-50"
                          aria-label={`Open campaign ${campaign.id}`}
                        >
                          <ExternalLink size={14} aria-hidden="true" />
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {visibleCampaigns.length === 0 ? (
            <div className="border-t border-line p-8 text-center text-sm text-slate-500">No campaigns match this risk view.</div>
          ) : null}
        </div>
      )}
    </>
  );
}
