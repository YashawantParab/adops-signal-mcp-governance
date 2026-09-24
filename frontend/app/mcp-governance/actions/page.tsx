"use client";

import Link from "next/link";
import { CheckCircle2, PlayCircle, RotateCcw, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { PageHeader } from "@/components/PageHeader";
import { RiskBadge } from "@/components/RiskBadge";
import { ErrorState, LoadingState } from "@/components/StateViews";
import { api, DEMO_VIEWER_ROLE, formatDateTime } from "@/lib/api";
import type { ActionType, CampaignSummary, ProposedAction } from "@/types";

const ACTION_TYPES: { value: ActionType; label: string }[] = [
  { value: "adjust_frequency_cap", label: "Adjust frequency cap" },
  { value: "relax_device_constraint", label: "Relax device constraint" },
  { value: "pause_campaign", label: "Pause campaign" },
  { value: "resume_campaign", label: "Resume campaign" }
];

function ParamsForm({
  actionType,
  onChange
}: {
  actionType: ActionType;
  onChange: (params: Record<string, unknown>) => void;
}) {
  if (actionType === "adjust_frequency_cap") {
    return (
      <label className="block">
        <span className="text-sm font-medium text-slate-700">New frequency cap</span>
        <input
          type="number"
          min={1}
          max={20}
          defaultValue={3}
          onChange={(event) => onChange({ new_frequency_cap: Number(event.target.value) })}
          className="focus-ring mt-2 w-full rounded-md border border-line px-3 py-2 text-sm"
        />
      </label>
    );
  }
  if (actionType === "relax_device_constraint") {
    return (
      <label className="block">
        <span className="text-sm font-medium text-slate-700">Device to add</span>
        <select
          defaultValue="Mobile"
          onChange={(event) => onChange({ add_device: event.target.value })}
          className="focus-ring mt-2 w-full rounded-md border border-line bg-white px-3 py-2 text-sm"
        >
          {["CTV", "Desktop", "Mobile", "Tablet"].map((device) => (
            <option key={device} value={device}>
              {device}
            </option>
          ))}
        </select>
      </label>
    );
  }
  return <p className="text-sm text-slate-500">No parameters needed.</p>;
}

export default function ActionConsolePage() {
  const { user } = useAuth();
  const isDemoViewer = user?.role === DEMO_VIEWER_ROLE;

  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [actions, setActions] = useState<ProposedAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const [campaignId, setCampaignId] = useState<number | "">("");
  const [actionType, setActionType] = useState<ActionType>("adjust_frequency_cap");
  const [params, setParams] = useState<Record<string, unknown>>({ new_frequency_cap: 3 });
  const [rationaleById, setRationaleById] = useState<Record<number, string>>({});

  function load() {
    setLoading(true);
    setError(null);
    Promise.all([api.campaigns(), api.actions()])
      .then(([campaignList, actionList]) => {
        setCampaigns(campaignList);
        setActions(actionList);
        setCampaignId((current) => current || campaignList[0]?.id || "");
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function propose(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!campaignId) return;
    setBusyId(-1);
    try {
      await api.proposeAction(Number(campaignId), actionType, params);
      load();
    } catch (err) {
      setError(err);
    } finally {
      setBusyId(null);
    }
  }

  async function approve(action: ProposedAction) {
    const rationale = rationaleById[action.id]?.trim();
    if (!rationale || rationale.length < 3) return;
    setBusyId(action.id);
    try {
      await api.approveAction(action.id, rationale);
      load();
    } catch (err) {
      setError(err);
    } finally {
      setBusyId(null);
    }
  }

  async function execute(action: ProposedAction) {
    setBusyId(action.id);
    try {
      await api.executeAction(action.id);
      load();
    } catch (err) {
      setError(err);
    } finally {
      setBusyId(null);
    }
  }

  async function rollback(action: ProposedAction) {
    setBusyId(action.id);
    try {
      await api.rollbackAction(action.id);
      load();
    } catch (err) {
      setError(err);
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <LoadingState label="Loading synthetic action console" />;

  return (
    <>
      <PageHeader
        title="Synthetic Action Console"
        subtitle="Propose a narrow, typed change to a synthetic campaign setting, route it through human approval, execute it, verify the resulting state, and roll it back if needed. No real ad server is involved."
      />
      {error ? (
        <div className="mb-5">
          <ErrorState error={error} onRetry={load} />
        </div>
      ) : null}

      <form onSubmit={propose} className="panel mb-6 rounded-md p-5">
        <div className="grid gap-4 lg:grid-cols-3">
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Campaign</span>
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
            <span className="text-sm font-medium text-slate-700">Action</span>
            <select
              value={actionType}
              onChange={(event) => {
                const next = event.target.value as ActionType;
                setActionType(next);
                setParams(next === "adjust_frequency_cap" ? { new_frequency_cap: 3 } : next === "relax_device_constraint" ? { add_device: "Mobile" } : {});
              }}
              className="focus-ring mt-2 w-full rounded-md border border-line bg-white px-3 py-2 text-sm"
            >
              {ACTION_TYPES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <div>
            <ParamsForm actionType={actionType} onChange={setParams} />
          </div>
        </div>
        <div className="mt-4 flex items-center justify-end gap-4">
          {isDemoViewer ? (
            <p className="text-sm text-slate-600">
              Public demo is read-only.{" "}
              <Link href="/" className="font-semibold text-accent hover:text-teal-700">
                Use the full demo login
              </Link>{" "}
              to propose a synthetic action.
            </p>
          ) : null}
          <button
            type="submit"
            disabled={!campaignId || busyId === -1 || isDemoViewer}
            className="focus-ring inline-flex items-center justify-center rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-60"
          >
            <PlayCircle className="mr-2" size={16} aria-hidden="true" />
            {busyId === -1 ? "Proposing..." : "Propose Action"}
          </button>
        </div>
      </form>

      <div className="space-y-3">
        {actions.length === 0 ? (
          <p className="panel rounded-md p-5 text-sm text-slate-500">No synthetic actions proposed yet.</p>
        ) : null}
        {actions.map((action) => {
          const latestExecution = action.executions[action.executions.length - 1];
          const latestVerification = latestExecution?.verifications[latestExecution.verifications.length - 1];
          const latestRollback = latestExecution?.rollbacks[latestExecution.rollbacks.length - 1];
          return (
            <div key={action.id} className="panel rounded-md p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase text-accent">
                    Campaign {action.campaign_id}
                    {action.campaign_name ? ` · ${action.campaign_name}` : ""}
                  </p>
                  <h3 className="mt-1 text-base font-semibold text-ink">{action.action_type.replaceAll("_", " ")}</h3>
                  <p className="mt-1 text-xs text-slate-500">
                    Requested: <span className="font-mono">{JSON.stringify(action.requested_params)}</span>
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <RiskBadge value={action.risk_class} />
                  <RiskBadge value={action.status} />
                </div>
              </div>

              {latestExecution ? (
                <div className="mt-3 grid gap-2 rounded-md border border-line bg-slate-50 p-3 text-xs sm:grid-cols-3">
                  <div>
                    <p className="font-semibold uppercase text-slate-500">Before</p>
                    <p className="mt-1 font-mono">{JSON.stringify(latestExecution.before_state)}</p>
                  </div>
                  <div>
                    <p className="font-semibold uppercase text-slate-500">After</p>
                    <p className="mt-1 font-mono">{JSON.stringify(latestExecution.after_state)}</p>
                  </div>
                  <div>
                    <p className="font-semibold uppercase text-slate-500">Verification</p>
                    <p className="mt-1 flex items-center gap-1">
                      {latestVerification ? (
                        <>
                          {latestVerification.verification_status === "verified" ? (
                            <CheckCircle2 size={14} className="text-emerald-600" aria-hidden="true" />
                          ) : (
                            <ShieldAlert size={14} className="text-red-600" aria-hidden="true" />
                          )}
                          {latestVerification.verification_status}
                        </>
                      ) : (
                        "pending"
                      )}
                    </p>
                  </div>
                </div>
              ) : null}

              {latestRollback ? (
                <p className="mt-2 text-xs text-slate-500">
                  Rolled back {formatDateTime(latestRollback.rolled_back_at)} · restored state{" "}
                  <span className="font-mono">{JSON.stringify(latestRollback.restored_state)}</span> ·{" "}
                  {latestRollback.verification_status}
                </p>
              ) : null}

              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3">
                {action.status === "pending_approval" && !isDemoViewer ? (
                  <>
                    <input
                      type="text"
                      placeholder="Approval rationale"
                      value={rationaleById[action.id] ?? ""}
                      onChange={(event) => setRationaleById((current) => ({ ...current, [action.id]: event.target.value }))}
                      className="focus-ring w-64 rounded-md border border-line px-3 py-2 text-xs"
                    />
                    <button
                      type="button"
                      onClick={() => approve(action)}
                      disabled={busyId === action.id || (rationaleById[action.id]?.trim().length ?? 0) < 3}
                      className="focus-ring inline-flex items-center rounded-md bg-ink px-3 py-2 text-xs font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
                    >
                      Approve
                    </button>
                  </>
                ) : null}
                {action.status === "approved" && !isDemoViewer ? (
                  <button
                    type="button"
                    onClick={() => execute(action)}
                    disabled={busyId === action.id}
                    className="focus-ring inline-flex items-center rounded-md bg-ink px-3 py-2 text-xs font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
                  >
                    <PlayCircle className="mr-1" size={14} aria-hidden="true" />
                    Execute
                  </button>
                ) : null}
                {(action.status === "executed" || action.status === "verified") && !isDemoViewer ? (
                  <button
                    type="button"
                    onClick={() => rollback(action)}
                    disabled={busyId === action.id}
                    className="focus-ring inline-flex items-center rounded-md border border-line px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                  >
                    <RotateCcw className="mr-1" size={14} aria-hidden="true" />
                    Roll back
                  </button>
                ) : null}
                {action.status === "blocked" ? (
                  <p className="text-xs text-red-700">CRITICAL campaign risk - blocked before it could reach approval.</p>
                ) : null}
                <span className="ml-auto text-xs text-slate-400">
                  Proposed by {action.proposed_by} · {formatDateTime(action.created_at)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
