"use client";

import { Activity, ArrowRight, LockKeyhole } from "lucide-react";
import { useState } from "react";

interface Props {
  onLogin: (email: string, password: string) => Promise<void>;
}

export function LoginScreen({ onLogin }: Props) {
  const [email, setEmail] = useState("adops@demo.adops.local");
  const [password, setPassword] = useState("SignalDemo!2026");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await onLogin(email, password);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Sign in failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="grid min-h-screen bg-white lg:grid-cols-[1.05fr_0.95fr]">
      <section className="flex min-h-[420px] flex-col justify-between bg-ink p-8 text-white lg:p-14">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-md bg-white text-ink">
            <Activity size={21} aria-hidden="true" />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase text-emerald-300">AdOps</p>
            <p className="text-xl font-semibold">Signal</p>
          </div>
        </div>
        <div className="max-w-xl">
          <p className="text-sm font-semibold text-emerald-300">CTV delivery operations</p>
          <h1 className="mt-4 text-4xl font-semibold leading-tight lg:text-5xl">
            Diagnose campaign risk before it becomes a client escalation.
          </h1>
          <p className="mt-5 max-w-lg text-base leading-7 text-slate-300">
            Evidence-grounded campaign diagnosis across pacing, inventory, targeting, bids, and VAST quality, with human approval built in.
          </p>
        </div>
        <p className="text-xs text-slate-400">Synthetic portfolio environment. No customer or personal data.</p>
      </section>

      <section className="flex items-center justify-center bg-surface p-6 lg:p-12">
        <form onSubmit={submit} className="w-full max-w-md border border-line bg-white p-7 shadow-panel">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-emerald-50 text-accent">
            <LockKeyhole size={19} aria-hidden="true" />
          </div>
          <h2 className="mt-5 text-2xl font-semibold">Open the operations workspace</h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Demo credentials are prefilled for the AdOps Manager role.
          </p>
          <label className="mt-6 block">
            <span className="text-sm font-medium text-slate-700">Email</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="focus-ring mt-2 w-full rounded-md border border-line px-3 py-2.5 text-sm"
              autoComplete="username"
            />
          </label>
          <label className="mt-4 block">
            <span className="text-sm font-medium text-slate-700">Password</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="focus-ring mt-2 w-full rounded-md border border-line px-3 py-2.5 text-sm"
              autoComplete="current-password"
            />
          </label>
          {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}
          <button
            type="submit"
            disabled={loading}
            className="focus-ring mt-6 inline-flex w-full items-center justify-center rounded-md bg-ink px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-60"
          >
            {loading ? "Signing in..." : "Enter workspace"}
            {!loading ? <ArrowRight className="ml-2" size={16} aria-hidden="true" /> : null}
          </button>
        </form>
      </section>
    </main>
  );
}
