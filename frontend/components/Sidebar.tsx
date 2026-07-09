"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Bot, ClipboardCheck, History, LayoutDashboard, LogOut, Menu, TrendingUp, Tv, X } from "lucide-react";
import { useEffect, useState } from "react";

import { api, DEMO_VIEWER_ROLE } from "@/lib/api";
import type { SystemStatus } from "@/types";

import { useAuth } from "./AuthProvider";

const nav = [
  { href: "/dashboard", label: "Operations", icon: LayoutDashboard },
  { href: "/agent", label: "Investigations", icon: Bot },
  { href: "/vast-validator", label: "VAST Validator", icon: Tv },
  { href: "/recommendations", label: "Decision Queue", icon: ClipboardCheck },
  {
    href: "/audit-logs",
    label: "Governance Record",
    icon: History,
    roles: ["admin", "adops_manager", "product_manager", DEMO_VIEWER_ROLE]
  },
  { href: "/impact", label: "Business Impact", icon: TrendingUp }
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  // AppShell only renders the sidebar once a session exists, so user is
  // always set here in practice - the fallbacks below just keep the type
  // checker honest without changing behavior.
  const visibleNav = nav.filter((item) => !item.roles || item.roles.includes(user?.role ?? ""));

  useEffect(() => setMobileOpen(false), [pathname]);
  useEffect(() => {
    api.systemStatus().then(setSystemStatus).catch(() => setSystemStatus(null));
  }, []);

  return (
    <aside className="fixed inset-x-0 top-0 z-20 border-b border-line bg-white md:inset-y-0 md:left-0 md:right-auto md:w-64 md:border-b-0 md:border-r">
      <div className="flex h-16 items-center gap-3 px-5 md:h-20">
        <div className="flex h-10 w-10 items-center justify-center rounded-md bg-ink text-white">
          <Activity size={20} aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <h1 className="whitespace-nowrap text-lg font-semibold leading-tight text-ink">
            SignalOps <span className="text-accent">AI</span>
          </h1>
          <p className="text-xs font-medium text-slate-400">Delivery intelligence</p>
        </div>
        <button
          type="button"
          onClick={() => setMobileOpen((current) => !current)}
          className="focus-ring ml-auto flex h-10 w-10 items-center justify-center rounded-md text-slate-600 hover:bg-slate-100 md:hidden"
          aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={mobileOpen}
        >
          {mobileOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
        </button>
      </div>
      <nav
        className={`${mobileOpen ? "block" : "hidden"} absolute inset-x-0 top-16 border-t border-line bg-white px-3 py-3 shadow-panel md:static md:block md:space-y-1 md:border-0 md:py-0 md:shadow-none`}
      >
        {visibleNav.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`focus-ring flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition ${
                active ? "bg-ink text-white" : "text-slate-600 hover:bg-slate-100 hover:text-ink"
              }`}
            >
              <Icon size={18} aria-hidden="true" />
              {item.label}
            </Link>
          );
        })}
        <div className="mt-3 flex items-center justify-between border-t border-line px-3 pt-3 md:hidden">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-ink">{user?.full_name}</p>
            <p className="truncate text-xs capitalize text-slate-500">{user?.role.replace("_", " ")}</p>
          </div>
          <button
            type="button"
            onClick={logout}
            className="focus-ring flex h-9 w-9 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100"
            aria-label="Sign out"
          >
            <LogOut size={17} aria-hidden="true" />
          </button>
        </div>
      </nav>
      <div className="hidden border-t border-line p-4 md:absolute md:bottom-0 md:block md:w-full">
        <div className="mb-4 border-b border-line pb-4">
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="flex items-center gap-2 font-medium text-slate-600">
              <span className={`h-2 w-2 rounded-full ${systemStatus?.status === "operational" ? "bg-emerald-500" : "bg-amber-500"}`} />
              Platform {systemStatus?.status ?? "checking"}
            </span>
            <span className="font-medium text-slate-400">v{systemStatus?.version ?? "-"}</span>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            {systemStatus?.ai_mode === "llm_rag" ? "LLM + RAG reasoning" : "Grounded fallback mode"}
          </p>
        </div>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-ink">{user?.full_name}</p>
            <p className="truncate text-xs capitalize text-slate-500">{user?.role.replace("_", " ")}</p>
          </div>
          <button
            type="button"
            onClick={logout}
            className="focus-ring flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-ink"
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut size={17} aria-hidden="true" />
          </button>
        </div>
      </div>
    </aside>
  );
}
