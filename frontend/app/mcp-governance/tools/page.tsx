"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { RiskBadge } from "@/components/RiskBadge";
import { ErrorState, LoadingState } from "@/components/StateViews";
import { api, formatDateTime, formatNumber, formatPercent } from "@/lib/api";
import type { MCPToolDescriptor } from "@/types";

export default function MCPToolRegistryPage() {
  const [tools, setTools] = useState<MCPToolDescriptor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  function load() {
    setLoading(true);
    setError(null);
    api
      .mcpTools()
      .then(setTools)
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  if (loading) return <LoadingState label="Loading MCP tool registry" />;
  if (error) return <ErrorState error={error} onRetry={load} />;

  return (
    <>
      <PageHeader
        title="MCP Tool Registry"
        subtitle="Every tool the governed MCP agent can call: its permission surface, approval posture, and recent usage reliability."
      />

      <section className="panel overflow-hidden rounded-md">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-line text-sm">
            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Tool</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Permission level</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Approval required</th>
                <th className="px-4 py-3">Risk level</th>
                <th className="px-4 py-3">Last used</th>
                <th className="px-4 py-3">Failure rate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line bg-white">
              {tools.map((tool) => (
                <tr key={tool.name} className="align-top hover:bg-slate-50">
                  <td className="px-4 py-4">
                    <p className="font-semibold text-ink">{tool.name}</p>
                    <p className="mt-1 max-w-xs text-xs leading-5 text-slate-500">{tool.description}</p>
                    <p className="mt-1 text-xs text-slate-400">{formatNumber(tool.call_count)} call(s) recorded</p>
                  </td>
                  <td className="px-4 py-4 text-slate-700">{tool.category}</td>
                  <td className="px-4 py-4 capitalize text-slate-700">{tool.permission_level}</td>
                  <td className="px-4 py-4">
                    <span
                      className={`inline-flex items-center rounded-md border px-2 py-1 text-xs font-semibold ${
                        tool.read_only ? "border-slate-200 bg-slate-50 text-slate-600" : "border-amber-200 bg-amber-50 text-amber-700"
                      }`}
                    >
                      {tool.read_only ? "Read-only" : "Action"}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    <span
                      className={`inline-flex items-center rounded-md border px-2 py-1 text-xs font-semibold ${
                        tool.approval_required ? "border-amber-200 bg-amber-50 text-amber-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"
                      }`}
                    >
                      {tool.approval_required ? "Required" : "Not required"}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    <RiskBadge value={tool.risk_level} />
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-xs text-slate-500">
                    {tool.last_used_at ? formatDateTime(tool.last_used_at) : "Never"}
                  </td>
                  <td className="px-4 py-4">{formatPercent(tool.failure_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
