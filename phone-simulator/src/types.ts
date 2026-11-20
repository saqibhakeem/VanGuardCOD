export type CallDirection = "OUTBOUND_VERIFY" | "INBOUND_RESCUE";
export type CallStatus = "ACTIVE" | "PAUSED_APPROVAL" | "COMPLETED" | "FAILED";
export type CallerRole = "customer" | "rider";

export interface Order {
  id: string;
  tenant_id: string;
  external_order_id: string;
  customer_name: string;
  customer_phone: string;
  items_summary: string;
  cod_amount: number;
  raw_address: string;
  verified_landmark: string | null;
  delivery_window: string | null;
  rto_risk_score: number;
  status: string;
  call_attempts?: number;
  max_call_attempts?: number;
  next_retry_at?: string | null;
  last_call_at?: string | null;
  created_at: string;
}

export interface CallTrigger {
  session_id: string;
  ws_url: string;
  direction: CallDirection;
  status: CallStatus;
  order: Order;
  store_name?: string | null;
}

export type TranscriptRole = "user" | "assistant" | "system";

export interface TranscriptEntry {
  id: string;
  role: TranscriptRole;
  text: string;
  at: number;
}

export interface ToolTraceEntry {
  id: string;
  step: number;
  tool_name: string;
  arguments: Record<string, unknown>;
  duration_ms: number;
  status: string;
  result?: unknown;
  error?: string | null;
  approval_id?: string | null;
  at: number;
}

export interface Telemetry {
  stt_ms: number;
  llm_ms: number;
  tts_ms: number;
  total_ms: number;
}

export type CallPhase =
  | "idle"
  | "connecting"
  | "live"
  | "ending"
  | "reconnecting"
  | "ended"
  | "missed"
  | "error";

export interface CallTimeoutResponse {
  session_id: string;
  status: string;
  order_id: string;
  order_status: string;
  call_attempts: number;
  max_call_attempts: number;
  next_retry_at: string | null;
}

export interface ActiveCall {
  sessionId: string;
  wsUrl: string;
  direction: CallDirection;
  order: Order;
  startedAt: number;
}
