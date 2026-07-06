import { formatPercent } from "@/lib/api";
import type { CampaignDetail } from "@/types";

import { RiskBadge } from "./RiskBadge";

export function PacingChart({ history }: { history: CampaignDetail["pacing_history"] }) {
  const maxValue = Math.max(...history.map((item) => Math.max(item.expected_delivery, item.actual_delivery)), 1);
  return (
    <div className="panel rounded-md p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold">Pacing Trend</h2>
        <span className="text-xs text-slate-500">Expected vs actual</span>
      </div>
      <div className="space-y-4">
        {history.map((item) => (
          <div key={item.date} className="grid gap-2 md:grid-cols-[96px_1fr_90px] md:items-center">
            <span className="text-sm text-slate-600">{new Date(item.date).toLocaleDateString()}</span>
            <div className="space-y-1">
              <div className="h-2 rounded bg-slate-100">
                <div className="h-2 rounded bg-slate-300" style={{ width: `${(item.expected_delivery / maxValue) * 100}%` }} />
              </div>
              <div className="h-2 rounded bg-slate-100">
                <div className="h-2 rounded bg-accent" style={{ width: `${(item.actual_delivery / maxValue) * 100}%` }} />
              </div>
            </div>
            <div className="flex items-center justify-between gap-2 md:justify-end">
              <span className="text-sm font-medium">{formatPercent(item.pacing_percentage)}</span>
              <RiskBadge value={item.risk_level} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
