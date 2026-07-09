import { ShieldCheck } from "lucide-react";

export function ClientSafeBrief({ summary, omittedInternalDetails }: { summary: string; omittedInternalDetails: string[] }) {
  return (
    <div className="border-l-4 border-accent bg-emerald-50 p-4">
      <div className="flex items-center gap-2">
        <ShieldCheck className="text-emerald-700" size={16} aria-hidden="true" />
        <p className="text-xs font-semibold uppercase text-emerald-800">Client-safe brief</p>
      </div>
      <p className="mt-2 text-sm leading-6 text-slate-700">{summary}</p>
      <p className="mt-3 text-xs leading-5 text-emerald-800">
        Generated from the diagnosis evidence above for external communication. It omits {omittedInternalDetails.join(", ")} and
        does not state anything the evidence does not support.
      </p>
    </div>
  );
}
