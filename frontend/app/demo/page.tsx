"use client";

import DashboardPage from "@/app/dashboard/page";

/**
 * AuthProvider starts a read-only demo session as soon as it sees this
 * route (see isDemoPath in AuthProvider.tsx), and AppShell holds off
 * rendering this component until that session's user exists - so by the
 * time this renders, the visitor is already authenticated. No redirect hop
 * is needed: the dashboard renders directly at /demo.
 */
export default function PublicDemoPage() {
  return <DashboardPage />;
}
