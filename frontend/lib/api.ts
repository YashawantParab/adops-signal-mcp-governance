import type {
  AgentDiagnosis,
  AuditLog,
  CampaignDetail,
  CampaignHealth,
  CampaignSummary,
  ClientSummaryResponse,
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
const REQUEST_TIMEOUT_MS = 20_000;

export const DEMO_VIEWER_ROLE = "demo_viewer";

/**
 * Thrown when the backend cannot be reached at all (network failure or our
 * own request timeout) as opposed to a real HTTP error response. Render's
 * free tier can take up to ~60s to wake a sleeping instance, so this is
 * treated as "still waking up," not "broken" - see StateViews.ErrorState.
 */
export class BackendUnavailableError extends Error {
  constructor() {
    super("Waking demo backend. This may take up to 60 seconds on the free hosting tier.");
    this.name = "BackendUnavailableError";
  }
}

export function isBackendUnavailable(error: unknown): boolean {
  return error instanceof BackendUnavailableError;
}

export function getAuthToken(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
}

/**
 * FastAPI error bodies aren't always a plain string: validation failures
 * (422) send `detail` as an array of {loc, msg, type} objects. Stringifying
 * that directly (or handing it to `new Error()`) produces "[object Object]"
 * in the UI, so every shape is normalized to readable text here.
 */
function formatErrorDetail(detail: unknown): string {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          const entry = item as { loc?: unknown[]; msg?: string };
          const field = Array.isArray(entry.loc) ? entry.loc.filter((part) => part !== "body").join(".") : "";
          return field ? `${field}: ${entry.msg}` : String(entry.msg ?? "");
        }
        return "";
      })
      .filter(Boolean)
      .join("; ");
  }
  if (typeof detail === "object" && "msg" in (detail as Record<string, unknown>)) {
    return String((detail as { msg?: unknown }).msg ?? "");
  }
  return "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getAuthToken();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {})
      },
      cache: "no-store",
      signal: controller.signal
    });
  } catch {
    throw new BackendUnavailableError();
  } finally {
    clearTimeout(timeout);
  }
  if (!response.ok) {
    if (response.status === 401) clearAuthToken();
    const text = await response.text();
    let payload: { detail?: unknown } | null = null;
    try {
      payload = JSON.parse(text) as { detail?: unknown };
    } catch {
      throw new Error(text || `Request failed with ${response.status}`);
    }
    throw new Error(formatErrorDetail(payload?.detail) || `Request failed with ${response.status}`);
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
  startDemoSession: () => request<AuthResponse>("/api/auth/demo-session", { method: "POST" }),
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
    request<ClientSummaryResponse>("/api/agent/generate-client-summary", {
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

/**
 * Compact form for tight KPI tiles, e.g. 2147000 -> "2.15M", 54000 -> "54K".
 * Use formatNumber() instead when full precision matters (tables, exports).
 */
export function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 }).format(value);
}

export function formatPercent(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? `${rounded}%` : `${rounded.toFixed(1)}%`;
}

export function formatCurrency(value: number, fractionDigits = 0): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits
  }).format(value);
}

/**
 * Compact currency for tight KPI tiles, e.g. 201000 -> "€201k", 1400000 -> "€1.4M".
 * Use formatCurrency() instead when full precision matters.
 */
export function formatCompactCurrency(value: number): string {
  const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);
  return `€${compact.replace(/K$/, "k")}`;
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
