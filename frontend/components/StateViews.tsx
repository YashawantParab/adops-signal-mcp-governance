import { AlertCircle, Loader2, RefreshCw } from "lucide-react";

import { isBackendUnavailable } from "@/lib/api";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="panel flex min-h-48 items-center justify-center rounded-md p-8 text-slate-500">
      <Loader2 className="mr-2 animate-spin" size={18} aria-hidden="true" />
      {label}
    </div>
  );
}

export function ErrorState({ message, error, onRetry }: { message?: string; error?: unknown; onRetry?: () => void }) {
  const waking = isBackendUnavailable(error);
  const fallback = error instanceof Error ? error.message : typeof error === "string" ? error : "Something went wrong.";
  const text = waking ? "Waking demo backend. This may take up to 60 seconds on the free hosting tier." : message ?? fallback;
  return (
    <div
      className={`panel flex min-h-32 flex-col gap-3 rounded-md p-5 sm:flex-row sm:items-center sm:justify-between ${
        waking ? "border-amber-200 bg-amber-50 text-amber-800" : "border-red-200 bg-red-50 text-red-700"
      }`}
    >
      <span className="flex items-start gap-2 text-sm">
        <AlertCircle className="mt-0.5 shrink-0" size={18} aria-hidden="true" />
        {text}
      </span>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className={`focus-ring inline-flex shrink-0 items-center justify-center rounded-md border px-3 py-2 text-sm font-semibold ${
            waking ? "border-amber-300 bg-white text-amber-800 hover:bg-amber-100" : "border-red-300 bg-white text-red-700 hover:bg-red-100"
          }`}
        >
          <RefreshCw className="mr-2" size={15} aria-hidden="true" />
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="panel rounded-md p-8 text-center">
      <h3 className="text-base font-semibold">{title}</h3>
      <p className="mt-2 text-sm text-slate-500">{body}</p>
    </div>
  );
}
