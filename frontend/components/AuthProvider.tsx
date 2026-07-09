"use client";

import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";

import { api, clearAuthToken, getAuthToken, isBackendUnavailable, setAuthToken } from "@/lib/api";
import type { User } from "@/types";

/**
 * Shared predicate for "is this route the public demo." Used by AuthProvider
 * (to auto-start a demo session) and by AppShell (to decide whether a route
 * requires a real login). Keep both in sync by always importing this instead
 * of re-deriving the check.
 */
export function isDemoPath(pathname: string | null): boolean {
  return pathname === "/demo" || pathname?.startsWith("/demo/") === true;
}

interface AuthContextValue {
  user: User | null;
  ready: boolean;
  bootError: unknown;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  retryBootstrap: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider");
  return value;
}

/**
 * Pure context provider - it never decides what to render for a route. That
 * decision (show login, show a loading state, show protected content) lives
 * in AppShell, which knows about routes. This provider only knows about
 * auth/demo *state*, and always renders {children} so /demo (and every
 * other route) always gets to mount and run its own logic.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isDemoRoute = isDemoPath(pathname);
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [bootError, setBootError] = useState<unknown>(null);

  function bootstrap() {
    setReady(false);
    setBootError(null);
    const token = getAuthToken();
    if (token) {
      // An existing session (real login or a previously issued public-demo
      // token) always wins - /demo never downgrades an already authenticated
      // visitor, and a network hiccup here must not silently log them out.
      api
        .me()
        .then(setUser)
        .catch((err) => {
          if (isBackendUnavailable(err)) setBootError(err);
          else clearAuthToken();
        })
        .finally(() => setReady(true));
      return;
    }
    if (isDemoRoute) {
      api
        .startDemoSession()
        .then((response) => {
          setAuthToken(response.access_token);
          setUser(response.user);
        })
        .catch(setBootError)
        .finally(() => setReady(true));
      return;
    }
    setReady(true);
  }

  useEffect(() => {
    // Re-run whenever the route moves into/out of /demo (client-side
    // navigation doesn't remount this provider - it lives in the root
    // layout). Skip once a user session exists so this never re-fetches or
    // downgrades an already authenticated visitor on route changes.
    if (user) return;
    bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDemoRoute, user]);

  async function login(email: string, password: string) {
    const response = await api.login(email, password);
    setAuthToken(response.access_token);
    setUser(response.user);
  }

  function logout() {
    clearAuthToken();
    setUser(null);
  }

  const value: AuthContextValue = { user, ready, bootError, login, logout, retryBootstrap: bootstrap };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
