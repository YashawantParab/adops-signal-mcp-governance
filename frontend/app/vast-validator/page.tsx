"use client";

import Link from "next/link";
import { SearchCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { RiskBadge } from "@/components/RiskBadge";
import { ErrorState, LoadingState } from "@/components/StateViews";
import { WorkflowBar } from "@/components/WorkflowBar";
import { api } from "@/lib/api";
import type { CampaignDetail, CampaignSummary, VastValidationResponse } from "@/types";

export default function VastValidatorPage() {
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [campaign, setCampaign] = useState<CampaignDetail | null>(null);
  const [campaignId, setCampaignId] = useState<number | "">("");
  const [creativeId, setCreativeId] = useState<number | "">("");
  const [vastUrl, setVastUrl] = useState("");
  const [result, setResult] = useState<VastValidationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<unknown>(null);

  function loadCampaigns() {
    setLoading(true);
    setError(null);
    api
      .campaigns()
      .then((items) => {
        setCampaigns(items);
        setCampaignId(items[0]?.id || "");
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(loadCampaigns, []);

  useEffect(() => {
    if (!campaignId) return;
    api
      .campaign(Number(campaignId))
      .then((detail) => {
        setCampaign(detail);
        setCreativeId(detail.creatives[0]?.id || "");
        setResult(null);
      })
      .catch(setError);
  }, [campaignId]);

  const selectedCreative = useMemo(() => campaign?.creatives.find((creative) => creative.id === creativeId), [campaign, creativeId]);

  async function validate() {
    setValidating(true);
    setError(null);
    try {
      const response = await api.validateVast(creativeId ? Number(creativeId) : undefined, vastUrl || undefined);
      setResult(response);
    } catch (err) {
      setError(err);
    } finally {
      setValidating(false);
    }
  }

  if (loading) return <LoadingState label="Loading creatives" />;

  return (
    <>
      <PageHeader title="VAST Validator" subtitle="Review creative approval state and observed VAST runtime errors before diagnosing delivery impact." />
      <WorkflowBar currentStep={2} />
      {error ? <div className="mb-5"><ErrorState error={error} onRetry={campaigns.length ? undefined : loadCampaigns} /></div> : null}

      <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <section className="panel rounded-md p-5">
          <div className="space-y-4">
            <label className="block">
              <span className="text-sm font-medium text-slate-700">Campaign</span>
              <select
                value={campaignId}
                onChange={(event) => setCampaignId(Number(event.target.value))}
                className="focus-ring mt-2 w-full rounded-md border border-line px-3 py-2 text-sm"
              >
                {campaigns.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.id} - {item.campaign_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-sm font-medium text-slate-700">Creative</span>
              <select
                value={creativeId}
                onChange={(event) => setCreativeId(Number(event.target.value))}
                className="focus-ring mt-2 w-full rounded-md border border-line px-3 py-2 text-sm"
              >
                {campaign?.creatives.map((creative) => (
                  <option key={creative.id} value={creative.id}>
                    {creative.id} - {creative.creative_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-sm font-medium text-slate-700">Optional VAST URL</span>
              <input
                value={vastUrl}
                onChange={(event) => setVastUrl(event.target.value)}
                className="focus-ring mt-2 w-full rounded-md border border-line px-3 py-2 text-sm"
                placeholder="https://ads.example.test/vast/timeout"
              />
            </label>
            <button
              type="button"
              onClick={validate}
              className="focus-ring inline-flex w-full items-center justify-center rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-60"
              disabled={validating || (!creativeId && !vastUrl)}
            >
              <SearchCheck className="mr-2" size={16} aria-hidden="true" />
              {validating ? "Validating" : "Validate"}
            </button>
          </div>
        </section>

        <section className="panel rounded-md p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold">{selectedCreative?.creative_name ?? "Validation Result"}</h2>
              {selectedCreative ? <p className="mt-1 text-sm text-slate-500">{selectedCreative.vast_url}</p> : null}
            </div>
            {selectedCreative ? <RiskBadge value={selectedCreative.approval_status} /> : null}
          </div>

          {result ? (
            <div className="mt-5 space-y-4">
              <div className="rounded-md border border-line p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold">{result.valid ? "Valid" : "Needs attention"}</p>
                  <RiskBadge value={result.valid ? "valid" : "needs_review"} />
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-700">{result.suggested_fix}</p>
                {campaignId ? (
                  <Link
                    href={`/agent?campaignId=${campaignId}`}
                    className="mt-3 inline-flex text-sm font-semibold text-accent hover:text-teal-700"
                  >
                    Continue campaign investigation
                  </Link>
                ) : null}
              </div>
              <div>
                <h3 className="text-sm font-semibold">Errors</h3>
                <div className="mt-3 space-y-3">
                  {result.errors.length === 0 ? (
                    <p className="text-sm text-slate-500">No validation errors detected.</p>
                  ) : (
                    result.errors.map((error) => (
                      <div key={`${error.creative_id}-${error.error_code}-${error.detected_at}`} className="rounded-md border border-line p-3">
                        <div className="flex items-center justify-between gap-2">
                          <p className="font-medium">{error.error_code}</p>
                          <RiskBadge value={error.severity} />
                        </div>
                        <p className="mt-2 text-sm text-slate-600">{error.error_message}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          ) : (
            <p className="mt-5 text-sm text-slate-500">Select a creative and run validation.</p>
          )}
        </section>
      </div>
    </>
  );
}
