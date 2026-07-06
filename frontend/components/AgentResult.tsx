"use client";

import Link from "next/link";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { AgentDiagnosis } from "@/types";

import { RetrievedSources } from "./RetrievedSources";
import { RiskBadge } from "./RiskBadge";

const WORKFLOW_STEPS = [
  "Tool evidence",
  "RAG playbook lookup",
  "Structured diagnosis",
  "Recommendation created",
  "Client brief available",
  "Pending approval",
  "Governance record"
];

export function AgentResult({ result }: { result: AgentDiagnosis }) {
  const [toolDescriptions, setToolDescriptions] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;
    api
      .agentTools()
      .then((tools) => {
        if (cancelled) return;
        setToolDescriptions(Object.fromEntries(tools.map((tool) => [tool.name, tool.description])));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 text-xs font-medium text-slate-500">
        {WORKFLOW_STEPS.map((step, index) => (
          <span key={step} className="inline-flex items-center gap-1">
            <span className="rounded-md border border-line bg-slate-50 px-2 py-1">{step}</span>
            {index < WORKFLOW_STEPS.length - 1 ? <ArrowRight size={11} aria-hidden="true" /> : null}
          </span>
        ))}
      </div>

      <div className="panel rounded-md p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Diagnosis</h2>
            <p className="mt-1 text-xs font-semibold uppercase text-accent">
              Investigation lens: {result.query_intent.replaceAll("_", " ")}
            </p>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-700">{result.diagnosis}</p>
          </div>
          <div className="text-right">
            <div className="flex items-center justify-end gap-2">
              <div className="rounded-md border border-line bg-slate-50 px-3 py-2 text-sm font-semibold">
                {Math.round(result.confidence_score * 100)}% confidence
              </div>
              <RiskBadge value={result.risk_level} />
            </div>
            <p className="mt-2 text-xs text-slate-500">
              {result.execution_mode === "llm_rag" ? result.model_name : "Resilient fallback"} · {result.latency_ms} ms
            </p>
          </div>
        </div>
        {result.human_approval_required ? (
          <p className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            Human approval required before applying high-impact campaign changes.
          </p>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="panel rounded-md p-5">
          <h3 className="text-base font-semibold">Ranked Root Causes</h3>
          <div className="mt-4 space-y-3">
            {result.root_causes.map((cause) => (
              <div key={cause.cause} className="rounded-md border border-line p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-medium">{cause.cause}</p>
                  <RiskBadge value={cause.impact} />
                </div>
                <p className="mt-2 text-sm leading-5 text-slate-600">{cause.evidence}</p>
                {cause.evidence_ids.length ? (
                  <p className="mt-2 text-xs font-medium text-slate-400">{cause.evidence_ids.join(" · ")}</p>
                ) : null}
              </div>
            ))}
          </div>
        </section>

        <section className="panel rounded-md p-5">
          <h3 className="text-base font-semibold">Evidence</h3>
          <div className="mt-4 space-y-3">
            {result.evidence.map((item, index) => (
              <div key={`${item.source}-${index}`} id={item.id ?? undefined} className="rounded-md border border-line p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {item.id ? `${item.id} · ` : ""}
                    {item.source}
                  </p>
                  {item.metric ? <span className="text-xs font-medium text-accent">{item.metric}</span> : null}
                </div>
                <p className="mt-2 text-sm leading-5 text-slate-700">{item.message}</p>
              </div>
            ))}
          </div>
        </section>
      </div>

      <RetrievedSources sources={result.playbook_sources} />

      <section className="panel rounded-md p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold">Recommended Actions</h3>
            <p className="mt-1 text-sm text-slate-500">Actions remain pending until an authorized operator records a decision.</p>
          </div>
          <Link
            href={`/recommendations?campaignId=${result.campaign_id}`}
            className="focus-ring inline-flex items-center rounded-md border border-line px-3 py-2 text-sm font-semibold hover:bg-slate-50"
          >
            <ShieldCheck className="mr-2" size={16} aria-hidden="true" />
            Open approval queue
            <ArrowRight className="ml-2" size={14} aria-hidden="true" />
          </Link>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          {result.recommendations.map((recommendation) => (
            <div key={recommendation.id} className="rounded-md border border-line p-3">
              <div className="flex items-center justify-between gap-2">
                <RiskBadge value={recommendation.expected_impact} />
                <RiskBadge value={recommendation.status} />
              </div>
              <p className="mt-3 font-medium">{recommendation.title}</p>
              <p className="mt-2 text-sm leading-5 text-slate-600">{recommendation.description}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="panel rounded-md p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold">Execution Trace</h3>
            <p className="mt-1 text-sm text-slate-500">{result.prompt_version}</p>
          </div>
          <span className="rounded-md border border-line bg-slate-50 px-2 py-1 text-xs font-semibold uppercase text-slate-600">
            {result.execution_mode.replace("_", " + ")}
          </span>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <span className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">
            {result.query_intent.replaceAll("_", " ")}
          </span>
          {result.tools_called.map((tool) => (
            <span
              key={tool}
              title={toolDescriptions[tool] ?? tool}
              className="rounded-md border border-line bg-slate-50 px-2 py-1 text-xs font-medium text-slate-700"
            >
              {tool}
            </span>
          ))}
        </div>
        {result.retrieved_documents.length ? (
          <div className="mt-4 border-t border-line pt-4">
            <p className="text-xs font-semibold uppercase text-slate-500">Retrieved playbooks</p>
            <p className="mt-2 text-sm text-slate-700">{result.retrieved_documents.join(", ")}</p>
          </div>
        ) : null}
      </section>
    </div>
  );
}
