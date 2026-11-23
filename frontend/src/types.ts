export type OrderStatus =
  | "PENDING_CALL"
  | "CALLING"
  | "VERIFIED"
  | "CANCELLED"
  | "RESCHEDULED"
  | "NEEDS_APPROVAL"
  | "PENDING_RETRY"
  | "FAILED_CONTACT";

export type CallDirection = "OUTBOUND_VERIFY" | "INBOUND_RESCUE";

export type CallStatus = "ACTIVE" | "PAUSED_APPROVAL" | "COMPLETED" | "FAILED";

export type CallerRole = "customer" | "rider";

export type ApprovalStatus = "PENDING" | "APPROVED" | "REJECTED";

export type ChannelChoice = "TWILIO" | "WHATSAPP" | "BOTH";
export type WhatsAppProvider = "META" | "TWILIO";
export type OmnichannelStrategy = "WHATSAPP_FIRST" | "VOICE_FIRST";
export type VerificationChannel = "PHONE_CALL" | "WHATSAPP" | "OMNICHANNEL";

export interface ChannelConfig {
  channel_choice: ChannelChoice;
  twilio_account_sid?: string | null;
  twilio_auth_token?: string | null;
  twilio_from_number?: string | null;
  whatsapp_provider?: WhatsAppProvider;
  whatsapp_phone_number_id?: string | null;
  whatsapp_access_token?: string | null;
  whatsapp_waba_id?: string | null;
  whatsapp_verify_token?: string | null;
  omnichannel_strategy?: OmnichannelStrategy;
  is_twilio_verified: boolean;
  is_whatsapp_verified: boolean;
  active_channels: string[];
}

export interface ChannelConfigRequest {
  channel_choice: ChannelChoice;
  twilio_account_sid?: string | null;
  twilio_auth_token?: string | null;
  twilio_from_number?: string | null;
  whatsapp_provider?: WhatsAppProvider;
  whatsapp_phone_number_id?: string | null;
  whatsapp_access_token?: string | null;
  whatsapp_waba_id?: string | null;
  whatsapp_verify_token?: string | null;
  omnichannel_strategy?: OmnichannelStrategy;
}

export interface TestTwilioRequest {
  account_sid: string;
  auth_token: string;
  from_number: string;
}

export interface TestTwilioResponse {
  valid: boolean;
  message: string;
  friendly_name?: string | null;
  status?: string | null;
}

export interface TestWhatsAppRequest {
  provider: WhatsAppProvider;
  phone_number_id?: string | null;
  access_token?: string | null;
  waba_id?: string | null;
  twilio_account_sid?: string | null;
  twilio_auth_token?: string | null;
  twilio_from_number?: string | null;
}

export interface TestWhatsAppResponse {
  valid: boolean;
  message: string;
  verified_name?: string | null;
  display_phone_number?: string | null;
  quality_rating?: string | null;
}

export type ViewKey =
  | "operations"
  | "sessions"
  | "approvals"
  | "integrations"
  | "config";

export interface User {
  id: string;
  username: string;
  name: string;
  role: string;
  role_label: string;
  permissions: string[];
  tenant_id: string;
  tenant_name: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export interface RegisterStorePayload {
  store_name: string;
  admin_username: string;
  password: string;
  default_language?: string;
  voice_persona?: string;
  max_auto_approve_cod?: number;
  contact_phone?: string | null;
  channel_choice?: ChannelChoice;
  twilio_account_sid?: string | null;
  twilio_auth_token?: string | null;
  twilio_from_number?: string | null;
  whatsapp_provider?: WhatsAppProvider;
  whatsapp_phone_number_id?: string | null;
  whatsapp_access_token?: string | null;
  whatsapp_waba_id?: string | null;
  whatsapp_verify_token?: string | null;
  omnichannel_strategy?: OmnichannelStrategy;
}

export interface RegisterStoreResponse {
  token: string;
  api_key: string;
  tenant: TenantProfile;
  user: User;
  webhook_url: string;
}



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
  status: OrderStatus;
  verification_channel?: VerificationChannel | null;
  provider_reference_id?: string | null;
  delivery_status?: string | null;
  call_attempts?: number;
  max_call_attempts?: number;
  next_retry_at?: string | null;
  last_call_at?: string | null;
  created_at: string;
}

export interface CallTimeoutResponse {
  session_id: string;
  status: string;
  order_id: string;
  order_status: string;
  call_attempts: number;
  max_call_attempts: number;
  next_retry_at: string | null;
}

export interface CallSessionSummary {
  id: string;
  order_id: string;
  external_order_id: string;
  customer_name: string;
  direction: CallDirection;
  status: CallStatus;
  avg_turn_latency_ms: number;
  turn_count: number;
  created_at: string;
}

export interface CallTrigger {
  session_id: string;
  ws_url: string;
  direction: CallDirection;
  status: CallStatus;
  order: Order;
  store_name?: string | null;
  channel?: VerificationChannel | null;
  provider_call_sid?: string | null;
  message?: string | null;
}

export interface Approval {
  id: string;
  tenant_id: string;
  order_id: string;
  call_session_id: string;
  tool_name: string;
  proposed_arguments: Record<string, unknown>;
  reason: string;
  status: ApprovalStatus;
  created_at: string;
  current_values: Record<string, unknown>;
  order_reference: string | null;
}

export interface ResolveApprovalResponse {
  approval: Approval;
  approved: boolean;
  order: Order;
  call_session: {
    id: string;
    status: CallStatus;
    avg_turn_latency_ms: number;
  };
  tool_result: Record<string, unknown> | null;
}

export interface TenantProfile {
  id: string;
  name: string;
  default_language: string;
  voice_persona: string;
  max_auto_approve_cod: number;
  channel_choice?: ChannelChoice;
  twilio_account_sid?: string | null;
  twilio_from_number?: string | null;
  whatsapp_provider?: WhatsAppProvider;
  whatsapp_phone_number_id?: string | null;
  omnichannel_strategy?: OmnichannelStrategy;
  is_twilio_verified?: boolean;
  is_whatsapp_verified?: boolean;
}

export interface RuntimeConfig {
  tenant: TenantProfile;
  environment: string;
  api_prefix: string;
  mock_mode: boolean;
  stt_model: string;
  llm_model: string;
  fast_llm_model: string;
  tts_model: string;
  tts_default_voice: string;
  stt_language: string;
  llm_temperature: number;
  call_reconnect_grace_seconds: number;
}

export interface RtoAssessment {
  score: number;
  is_high_risk: boolean;
  has_house_number: boolean;
  address_word_count: number;
  missing_components: string[];
}

export interface IngestResponse {
  order: Order;
  rto: RtoAssessment;
  call_session: { id: string; status: CallStatus };
  session_id: string;
  ws_url: string;
}

export interface IngestPayload {
  external_order_id: string;
  customer_name: string;
  customer_phone: string;
  items_summary: string;
  cod_amount: number;
  raw_address: string;
  delivery_window?: string | null;
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

export interface LogEntry {
  id: string;
  at: number;
  name: string;
  detail: string;
}

export type CallPhase =
  | "idle"
  | "connecting"
  | "live"
  | "ending"
  | "reconnecting"
  | "ended"
  | "error";

export interface ActiveCall {
  sessionId: string;
  wsUrl: string;
  direction: CallDirection;
  order: Order;
  resumed: boolean;
  startedAt: number;
}
