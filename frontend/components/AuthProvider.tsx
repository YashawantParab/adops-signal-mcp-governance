"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { api, clearAuthToken, getAuthToken, setAuthToken } from "@/lib/api";
import type { User } from "@/types";

import { LoginScreen } from "./LoginScreen";

interface AuthContextValue {
  user: User;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider");
  return value;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getAuthToken()) {
      setReady(true);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => clearAuthToken())
      .finally(() => setReady(true));
  }, []);

  async function login(email: string, password: string) {
    const response = await api.login(email, password);
    setAuthToken(response.access_token);
    setUser(response.user);
  }

  function logout() {
    clearAuthToken();
    setUser(null);
  }

  const value = useMemo(() => (user ? { user, logout } : null), [user]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface text-sm text-slate-500">
        Securing workspace...
      </div>
    );
  }
  if (!user || !value) return <LoginScreen onLogin={login} />;
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
