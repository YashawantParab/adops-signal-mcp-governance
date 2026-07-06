import type { RiskLevel } from "@/types";

const styles: Record<string, string> = {
  Low: "border-emerald-200 bg-emerald-50 text-emerald-700",
  Medium: "border-amber-200 bg-amber-50 text-amber-700",
  High: "border-red-200 bg-red-50 text-red-700",
  low: "border-emerald-200 bg-emerald-50 text-emerald-700",
  medium: "border-amber-200 bg-amber-50 text-amber-700",
  high: "border-red-200 bg-red-50 text-red-700",
  Unknown: "border-slate-200 bg-slate-50 text-slate-600",
  pending: "border-slate-200 bg-slate-50 text-slate-600",
  valid: "border-emerald-200 bg-emerald-50 text-emerald-700",
  needs_review: "border-amber-200 bg-amber-50 text-amber-700",
  approved: "border-emerald-200 bg-emerald-50 text-emerald-700",
  rejected: "border-red-200 bg-red-50 text-red-700"
};

export function RiskBadge({ value }: { value: RiskLevel | string }) {
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-1 text-xs font-semibold ${styles[value] ?? styles.Unknown}`}>
      {value.replace("_", " ")}
    </span>
  );
}
