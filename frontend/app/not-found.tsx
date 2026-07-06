import Link from "next/link";
import { ArrowLeft, SearchX } from "lucide-react";

export default function NotFound() {
  return (
    <section className="flex min-h-[70vh] items-center justify-center">
      <div className="max-w-lg border border-line bg-white p-8 text-center shadow-panel">
        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-md bg-slate-100 text-slate-600">
          <SearchX size={20} aria-hidden="true" />
        </div>
        <p className="mt-5 text-xs font-semibold uppercase text-accent">Workspace navigation</p>
        <h1 className="mt-2 text-2xl font-semibold">This operational view is unavailable</h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          The address may be incomplete or no longer supported. Return to the campaign risk queue to continue working.
        </p>
        <Link
          href="/dashboard"
          className="focus-ring mt-6 inline-flex items-center rounded-md bg-ink px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-700"
        >
          <ArrowLeft className="mr-2" size={16} aria-hidden="true" />
          Return to campaign queue
        </Link>
      </div>
    </section>
  );
}
