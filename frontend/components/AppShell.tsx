"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { isDemoPath, useAuth } from "./AuthProvider";
import { DemoBanner } from "./DemoBanner";
import { ErrorState } from "./StateViews";
import { Sidebar } from "./Sidebar";

/**
 * Owns the app chrome (sidebar + page frame) and decides, per route, what an
 * unauthenticated visitor sees. AuthProvider only tracks *state* - this is
 * the one place that turns that state into "show login," "show the demo
 * workspace," or "show the protected page," so no route can get stuck
 * behind a global gate the way /demo previously did.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, ready, bootError, retryBootstrap } = useAuth();

  const isLoginRoute = pathname === "/";
  const isDemoRoute = isDemoPath(pathname);

  useEffect(() => {
    // Truly protected routes only: bounce to login once we know for sure
    // there's no session. Login and demo routes manage their own state.
    if (isLoginRoute || isDemoRoute) return;
    if (ready && !user) router.replace("/");
  }, [isLoginRoute, isDemoRoute, ready, user, router]);

  // The login page renders its own full-bleed layout - no sidebar chrome.
  if (isLoginRoute) return <>{children}</>;

  if (bootError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface p-6">
        <div className="w-full max-w-md">
          <ErrorState error={bootError} onRetry={retryBootstrap} />
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface text-sm text-slate-500">
        {isDemoRoute ? "Preparing the public demo workspace..." : "Securing workspace..."}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface text-ink">
      <Sidebar />
      <main className="min-h-screen px-4 pb-5 pt-20 md:ml-64 md:px-8 md:py-5 lg:px-10">
        <DemoBanner />
        {children}
      </main>
    </div>
  );
}
