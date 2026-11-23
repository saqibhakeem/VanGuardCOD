const API_PREFIX = "/api/v1";
const STORAGE_KEY = "vanguardcod.tenantKey";

export const DEFAULT_API_KEY = "vcod_live_demo_key_2026";

let tenantKey = readStoredKey();

function readStoredKey(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? DEFAULT_API_KEY;
  } catch {
    return DEFAULT_API_KEY;
  }
}

export function getTenantKey(): string {
  return tenantKey;
}

export function setTenantKey(value: string): void {
  tenantKey = value.trim();
  try {
    if (tenantKey) window.localStorage.setItem(STORAGE_KEY, tenantKey);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    return;
  }
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function describeDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return JSON.stringify(item);
      })
      .join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return "request failed";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (tenantKey) headers.set("X-Tenant-API-Key", tenantKey);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_PREFIX}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = response.statusText || `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (body && "detail" in body) message = describeDetail(body.detail);
    } catch {
      message = response.statusText || `HTTP ${response.status}`;
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function withApiKey(wsUrl: string): string {
  if (!tenantKey) return wsUrl;
  const url = new URL(wsUrl);
  url.searchParams.set("api_key", tenantKey);
  return url.toString();
}

export const api = {
  health: async (): Promise<{ status: string }> => {
    const response = await fetch("/health");
    if (!response.ok) throw new ApiError("health check failed", response.status);
    return (await response.json()) as { status: string };
  },

  orders: (signal?: AbortSignal) =>
    request<import("./types").Order[]>("/orders?limit=100", { signal }),

  pendingOutbound: (signal?: AbortSignal) =>
    request<import("./types").CallTrigger[]>("/calls/pending-outbound", { signal }),

  sessions: (limit = 100) =>
    request<import("./types").CallSessionSummary[]>(`/calls/sessions?limit=${limit}`),

  config: () => request<import("./types").RuntimeConfig>("/config"),

  approvals: (status = "PENDING") =>
    request<import("./types").Approval[]>(`/approvals?status=${status}&limit=100`),

  triggerOutbound: (orderId: string) =>
    request<import("./types").CallTrigger>(`/calls/trigger-outbound/${orderId}`, {
      method: "POST",
    }),

  startInbound: (orderId: string, role: import("./types").CallerRole) =>
    request<import("./types").CallTrigger>("/calls/start-inbound", {
      method: "POST",
      body: JSON.stringify({ order_id: orderId, caller_role: role }),
    }),

  declineCall: (sessionId: string) =>
    request<{ session_id: string; status: string }>(
      `/calls/${sessionId}/decline`,
      { method: "POST" },
    ),

  timeoutCall: (sessionId: string) =>
    request<import("./types").CallTimeoutResponse>(
      `/calls/${sessionId}/timeout`,
      { method: "POST" },
    ),

  retryOrder: (orderId: string) =>
    request<import("./types").CallTrigger>(
      `/calls/retry-order/${orderId}`,
      { method: "POST" },
    ),

  dispatchRetries: (force = true) =>
    request<{ dispatched_count: number; orders_retried: string[] }>(
      `/calls/dispatch-retries?force=${force}`,
      { method: "POST" },
    ),

  resolveApproval: (approvalId: string, approved: boolean, note: string) =>
    request<import("./types").ResolveApprovalResponse>(
      `/approvals/${approvalId}/resolve`,
      {
        method: "POST",
        body: JSON.stringify({
          approved,
          operator_note: note.trim() ? note.trim() : null,
        }),
      },
    ),

  ingestOrder: (payload: import("./types").IngestPayload) =>
    request<import("./types").IngestResponse>("/webhooks/orders", {
      method: "POST",
      body: JSON.stringify({ ...payload, payment_method: "COD" }),
    }),

  login: (username: string, password: string, tenantKey?: string) =>
    request<import("./types").LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password, tenant_key: tenantKey }),
    }),

  registerStore: (payload: import("./types").RegisterStorePayload) =>
    request<import("./types").RegisterStoreResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getMe: (role?: string) => {
    const headers: Record<string, string> = {};
    if (role) headers["X-User-Role"] = role;
    return request<import("./types").User>("/auth/me", { headers });
  },

  getChannelConfig: () =>
    request<import("./types").ChannelConfig>("/channels/config"),

  updateChannelConfig: (data: import("./types").ChannelConfigRequest) =>
    request<import("./types").ChannelConfig>("/channels/config", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  testTwilio: (data: import("./types").TestTwilioRequest) =>
    request<import("./types").TestTwilioResponse>("/channels/test-twilio", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  testWhatsApp: (data: import("./types").TestWhatsAppRequest) =>
    request<import("./types").TestWhatsAppResponse>("/channels/test-whatsapp", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  dispatchVerification: (orderId: string, channel?: string) =>
    request<import("./types").CallTrigger>(
      `/calls/dispatch-verification/${orderId}${channel ? `?channel=${encodeURIComponent(channel)}` : ""}`,
      { method: "POST" },
    ),
};
