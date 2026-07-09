"use client";

import { Info } from "lucide-react";

import { DEMO_VIEWER_ROLE } from "@/lib/api";

import { useAuth } from "./AuthProvider";

export function DemoBanner() {
  const { user } = useAuth();
  if (user?.role !== DEMO_VIEWER_ROLE) return null;
  return (
    <div className="mb-4 flex items-center gap-2 rounded-md border border-accent/30 bg-emerald-50 px-4 py-2.5 text-sm font-medium text-emerald-900">
      <Info className="shrink-0" size={16} aria-hidden="true" />
      Public portfolio demo · sample data · read-only workspace
    </div>
  );
}
