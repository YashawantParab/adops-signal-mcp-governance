"use client";

import { useSearchParams } from "next/navigation";
import { ShieldCheck } from "lucide-react";
import { Suspense, useEffect, useState } from "react";

import { MCPAgentRunResult } from "@/components/MCPAgentRunResult";
import { PageHeader } from "@/components/PageHeader";
import { ErrorState, LoadingState } from "@/components/StateViews";
import { api } from "@/lib/api";
import type { CampaignSummary, MCPAgentRunDetail, MCPAgentRunResponse, MCPToolDescriptor } from "@/types";

const DEFAULT_SEED_CAMPAIGN_ID = 1045;
const QUERY_PLACEHOLDER =
  "Example: Analyze campaign 1045, check delivery risk, review VAST errors, and prepare a safe recommendation.";

function AgentConsoleWorkspace() {
  const searchParams = useSearchParams();
  const initialCampaignId = Number(searchParams.get("campaignId")) || DEFAULT_SEED_CAMPAIGN_ID;

  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [campaignId, setCampaignId] = useState<number | "">("");
  const [query, setQuery] = useState("");
  const [loadingCampaigns, setLoadingCampaigns] = useState(true);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<MCPAgentRunResponse | null>(null);
  const [detail, setDetail] = useState<MCPAgentRunDetail | null>(null);
  const [toolDescriptions, setToolDescriptions] = useState<Record<string, MCPToolDescriptor>>({});
  const [error, setError] = useState<unknown>(null);

  function loadCampaigns() {
    setLoadingCampaigns(true);
    setError(null);
    api
      .campaigns()
      .then((items) => {
        setCampaigns(items);
        const seeded = items.some((item) => item.id === initialCampaignId) ? initialCampaignId : items[0]?.id;
        setCampaignId(seeded ?? DEFAULT_SEED_CAMPAIGN_ID);
      })
      .catch(setError)
      .finally(() => setLoadingCampaigns(false));
  }

  useEffect(loadCampaigns, [initialCampaignId]);

  useEffect(() => {
    api
      .mcpTools()
      .then((tools) => setToolDescriptions(Object.fromEntries(tools.map((tool) => [tool.name, tool]))))
      .catch(() => undefined);
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!campaignId || !query.trim()) return;
    setRunning(true);
    setError(null);
    setResult(null);
    setDetail(null);
    try {
      const run = await api.mcpAgentRun(query.trim(), String(campaignId));
      setResult(run);
      try {
        const runDetail = await api.mcpRunDetail(Number(run.agent_run_id));
        setDetail(runDetail);
      } catch {
        // Detail enrichment is best-effort - the primary run response above
        // already carries the summary, risk, and tool timeline.
      }
    } catch (err) {
      setError(err);
    } finally {
      setRunning(false);
    }
  }

  if (loadingCampaigns) return <LoadingState label="Loading MCP Agent Console" />;

  return (
    <>
      <PageHeader
        title="MCP Agent Console"
        subtitle="Run governed AdOps investigations through MCP tools, policy context, risk scoring, approval workflow, and audit logging."
      />
      {error ? (
        <div className="mb-5">
          <ErrorState error={error} onRetry={campaigns.length ? undefined : loadCampaigns} />
        </div>
      ) : null}

      <form onSubmit={submit} className="panel mb-6 rounded-md p-5">
        <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Campaign ID</span>
            <select
              value={campaignId}
              onChange={(event) => setCampaignId(Number(event.target.value))}
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
            <span className="text-sm font-medium text-slate-700">Ask the AdOps Governance Agent</span>
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              rows={2}
              className="focus-ring mt-2 w-full resize-none rounded-md border border-line px-3 py-2 text-sm"
              placeholder={QUERY_PLACEHOLDER}
            />
          </label>
        </div>
        <div className="mt-4 flex justify-end">
          <button
            type="submit"
            className="focus-ring inline-flex items-center justify-center rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-60"
            disabled={!campaignId || !query.trim() || running}
          >
            <ShieldCheck className="mr-2" size={16} aria-hidden="true" />
            {running ? "Running Governance Analysis" : "Run Governance Analysis"}
          </button>
        </div>
      </form>

      {running ? <LoadingState label="Running MCP tools, policy checks, and risk scoring" /> : null}

      {result && !running ? <MCPAgentRunResult result={result} detail={detail} toolDescriptions={toolDescriptions} /> : null}
    </>
  );
}

export default function MCPAgentConsolePage() {
  return (
    <Suspense fallback={<LoadingState label="Loading MCP Agent Console" />}>
      <AgentConsoleWorkspace />
    </Suspense>
  );
}
