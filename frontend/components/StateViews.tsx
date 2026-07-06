import { AlertCircle, Loader2 } from "lucide-react";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="panel flex min-h-48 items-center justify-center rounded-md p-8 text-slate-500">
      <Loader2 className="mr-2 animate-spin" size={18} aria-hidden="true" />
      {label}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="panel flex min-h-32 items-center rounded-md border-red-200 bg-red-50 p-5 text-red-700">
      <AlertCircle className="mr-2 shrink-0" size={18} aria-hidden="true" />
      <span className="text-sm">{message}</span>
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
