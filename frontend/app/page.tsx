"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { LoginScreen } from "@/components/LoginScreen";
import { useAuth } from "@/components/AuthProvider";

export default function Home() {
  const { user, ready, login } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (ready && user) router.replace("/dashboard");
  }, [ready, user, router]);

  if (!ready || user) return null;
  return <LoginScreen onLogin={login} />;
}
