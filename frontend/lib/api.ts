import type {
  AgentDiagnosis,
  AuditLog,
  CampaignDetail,
  CampaignHealth,
  CampaignSummary,
  Recommendation,
  AuthResponse,
  RoiAssumptions,
  RoiEstimate,
  SystemStatus,
  ToolDescriptor,
  User,
  VastValidationResponse
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/proxy";
const TOKEN_KEY = "adops-signal-token";

export function getAuthToken(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getAuthToken();
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {})
    },
    cache: "no-store"
  });
  if (!response.ok) {
    if (response.status === 401) clearAuthToken();
    const text = await response.text();
    try {
      const payload = JSON.parse(text) as { detail?: string };
      throw new Error(payload.detail || `Request failed with ${response.status}`);
    } catch (error) {
      if (error instanceof Error && error.message !== "Unexpected end of JSON input") throw error;
      throw new Error(text || `Request failed with ${response.status}`);
    }
  }
  return response.json() as Promise<T>;
}

export const api = {
  login: (email: string, password: string) =>
    request<AuthResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    }),
  me: () => request<User>("/api/auth/me"),
  systemStatus: () => request<SystemStatus>("/api/system/status"),
  campaigns: () => request<CampaignSummary[]>("/api/campaigns"),
  campaign: (id: number) => request<CampaignDetail>(`/api/campaigns/${id}`),
  health: (id: number) => request<CampaignHealth>(`/api/campaigns/${id}/health`),
  diagnose: (campaignId: number, query: string) =>
    request<AgentDiagnosis>("/api/agent/diagnose", {
      method: "POST",
      body: JSON.stringify({ campaign_id: campaignId, query })
    }),
  validateVast: (creativeId?: number, vastUrl?: string) =>
    request<VastValidationResponse>("/api/agent/validate-vast", {
      method: "POST",
      body: JSON.stringify({ creative_id: creativeId, vast_url: vastUrl })
    }),
  clientSummary: (campaignId: number, diagnosis?: string) =>
    request<{ campaign_id: number; summary: string; omitted_internal_details: string[] }>("/api/agent/generate-client-summary", {
      method: "POST",
      body: JSON.stringify({ campaign_id: campaignId, diagnosis })
    }),
  auditLogs: () => request<AuditLog[]>("/api/agent/audit-logs"),
  agentTools: () => request<ToolDescriptor[]>("/api/agent/tools"),
  recommendations: () => request<Recommendation[]>("/api/recommendations"),
  campaignRecommendations: (campaignId: number) => request<Recommendation[]>(`/api/recommendations/${campaignId}`),
  approveRecommendation: (id: number, reason: string) =>
    request<Recommendation>(`/api/recommendations/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ reason })
    }),
  rejectRecommendation: (id: number, reason: string) =>
    request<Recommendation>(`/api/recommendations/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason })
    }),
  estimateRoi: (assumptions: RoiAssumptions) =>
    request<RoiEstimate>("/api/insights/roi", {
      method: "POST",
      body: JSON.stringify(assumptions)
    })
};

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 10) / 10}%`;
}

export function formatCurrency(value: number, fractionDigits = 0): string {
  return new Intl.NumberFormat("en-DE", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits
  }).format(value);
}

/**
 * The backend stores and serializes timestamps as naive UTC (no "Z"/offset
 * suffix), so `new Date(value)` alone would parse them as local time. Force
 * UTC interpretation before formatting into an unambiguous "Jul 6, 2026 ·
 * 12:56" style string.
 */
export function formatDateTime(value: string): string {
  const hasTimezone = /Z$|[+-]\d{2}:?\d{2}$/.test(value);
  const date = new Date(hasTimezone ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return "Time unavailable";
  const datePart = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(date);
  const timePart = new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
  return `${datePart} · ${timePart}`;
}

export function formatReviewer(name?: string | null, role?: string | null, userId?: number | null): string {
  if (name) return role ? `${name} (${role.replaceAll("_", " ")})` : name;
  return userId ? `User ${userId}` : "Unknown reviewer";
}
