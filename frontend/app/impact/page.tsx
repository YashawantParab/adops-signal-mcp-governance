"use client";

import { Calculator, Clock3, Euro, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { StatCard } from "@/components/StatCard";
import { api, formatCurrency, formatNumber } from "@/lib/api";
import type { RoiAssumptions, RoiEstimate } from "@/types";

const defaults: RoiAssumptions = {
  campaigns_per_month: 250,
  incident_rate: 0.18,
  minutes_per_incident_before: 75,
  minutes_per_incident_after: 18,
  loaded_hourly_cost_eur: 58,
  average_campaign_value_eur: 18000,
  revenue_at_risk_rate: 0.08,
  recovery_rate: 0.25
};

const fields: Array<{
  key: keyof RoiAssumptions;
  label: string;
  suffix?: string;
  percent?: boolean;
}> = [
  { key: "campaigns_per_month", label: "Campaigns managed per month" },
  { key: "incident_rate", label: "Campaigns requiring investigation", suffix: "%", percent: true },
  { key: "minutes_per_incident_before", label: "Minutes per investigation today" },
  { key: "minutes_per_incident_after", label: "Minutes with Signal" },
  { key: "loaded_hourly_cost_eur", label: "Loaded operations cost", suffix: "EUR/hour" },
  { key: "average_campaign_value_eur", label: "Average campaign media value", suffix: "EUR" },
  { key: "revenue_at_risk_rate", label: "Media value at risk", suffix: "%", percent: true },
  { key: "recovery_rate", label: "Recoverable share of risk", suffix: "%", percent: true }
];

export default function ImpactPage() {
  const [assumptions, setAssumptions] = useState(defaults);
  const [estimate, setEstimate] = useState<RoiEstimate | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.estimateRoi(assumptions).then(setEstimate).catch((reason: Error) => setError(reason.message));
  }, [assumptions]);

  function update(key: keyof RoiAssumptions, value: number, percent: boolean) {
    setAssumptions((current) => ({ ...current, [key]: percent ? value / 100 : value }));
  }

  return (
    <>
      <PageHeader
        title="Business Impact Model"
        subtitle="A transparent value model for operational time saved and campaign revenue protected. Every assumption is editable."
      />
      {error ? <p className="mb-4 text-sm text-red-700">{error}</p> : null}

      <div className="mb-6 grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard label="Monthly incidents" value={formatNumber(estimate?.incidents_per_month ?? 0)} hint="Campaigns requiring diagnosis" />
        <StatCard label="Hours recovered" value={formatNumber(estimate?.hours_saved_per_month ?? 0)} hint="AdOps capacity per month" />
        <StatCard label="Monthly value" value={formatCurrency(estimate?.total_monthly_value_eur ?? 0)} hint="Labor plus protected media value" />
        <StatCard label="Annualized value" value={formatCurrency(estimate?.annualized_value_eur ?? 0)} hint="Directional, not a forecast" />
      </div>

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <section className="panel rounded-md p-5">
          <div className="flex items-center gap-3">
            <Calculator className="text-accent" size={20} aria-hidden="true" />
            <h2 className="text-base font-semibold">Operating assumptions</h2>
          </div>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            {fields.map((field) => (
              <label key={field.key} className="block">
                <span className="text-sm text-slate-600">{field.label}</span>
                <div className="mt-2 flex rounded-md border border-line bg-white focus-within:ring-2 focus-within:ring-accent">
                  <input
                    type="number"
                    min="0"
                    value={field.percent ? Math.round(assumptions[field.key] * 100) : assumptions[field.key]}
                    onChange={(event) => update(field.key, Number(event.target.value), Boolean(field.percent))}
                    className="min-w-0 flex-1 rounded-md px-3 py-2 text-sm outline-none"
                  />
                  {field.suffix ? <span className="border-l border-line px-3 py-2 text-xs text-slate-500">{field.suffix}</span> : null}
                </div>
              </label>
            ))}
          </div>
        </section>

        <section className="panel rounded-md p-5">
          <h2 className="text-base font-semibold">Value decomposition</h2>
          <div className="mt-5 space-y-4">
            <div className="flex items-start gap-3 border-b border-line pb-4">
              <Clock3 className="mt-0.5 text-accent" size={19} aria-hidden="true" />
              <div className="flex-1">
                <div className="flex justify-between gap-4">
                  <p className="font-medium">Operations capacity</p>
                  <p className="font-semibold">{formatCurrency(estimate?.labor_savings_eur ?? 0)}</p>
                </div>
                <p className="mt-1 text-sm leading-6 text-slate-500">
                  Investigation time reduced from {assumptions.minutes_per_incident_before} to {assumptions.minutes_per_incident_after} minutes.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 text-accent" size={19} aria-hidden="true" />
              <div className="flex-1">
                <div className="flex justify-between gap-4">
                  <p className="font-medium">Media value protected</p>
                  <p className="font-semibold">{formatCurrency(estimate?.revenue_protected_eur ?? 0)}</p>
                </div>
                <p className="mt-1 text-sm leading-6 text-slate-500">
                  Directional value from resolving delivery constraints earlier. This must be calibrated against real incident history.
                </p>
              </div>
            </div>
          </div>
          <div className="mt-6 rounded-md border border-emerald-200 bg-emerald-50 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-emerald-900">
              <Euro size={17} aria-hidden="true" />
              Decision use
            </div>
            <p className="mt-2 text-sm leading-6 text-emerald-800">
              Use this model to size a pilot and define measurement instrumentation. Do not present it as realized savings before a controlled rollout.
            </p>
          </div>
        </section>
      </div>
    </>
  );
}
