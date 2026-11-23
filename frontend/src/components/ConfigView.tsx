import {
  AlertCircle,
  ArrowUpRight,
  Check,
  CheckCircle2,
  Copy,
  Cpu,
  KeyRound,
  Layers,
  Loader2,
  MessageSquare,
  PhoneCall,
  Radio,
  Save,
  Server,
  ShieldCheck,
  Webhook,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { api } from "../api";
import type {
  ChannelChoice,
  ChannelConfig,
  OmnichannelStrategy,
  RuntimeConfig,
  TestTwilioResponse,
  TestWhatsAppResponse,
  WhatsAppProvider,
} from "../types";
import { Button, INPUT_CLASS, SectionLabel, SELECT_CLASS } from "./ui";

interface Props {
  config: RuntimeConfig | null;
  apiKey: string;
  onOpenWebhook: () => void;
}

function Card({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: LucideIcon;
  children: ReactNode;
}) {
  return (
    <section className="border border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-3 py-2">
        <Icon className="h-3.5 w-3.5 text-accent" aria-hidden />
        <SectionLabel>{title}</SectionLabel>
      </div>
      <div className="space-y-2.5 px-3 py-3 text-[11px] leading-4 text-ink-2">{children}</div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-line/60 pb-2 last:border-b-0 last:pb-0">
      <span className="shrink-0 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
        {label}
      </span>
      <span className="min-w-0 break-words text-right font-mono text-[10px] text-ink">
        {value}
      </span>
    </div>
  );
}

function CodeBlock({ code, label }: { code: string; label: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="border border-line bg-canvas/70">
      <div className="flex items-center justify-between border-b border-line px-2 py-1">
        <span className="font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
          {label}
        </span>
        <button
          type="button"
          onClick={() => void copy()}
          className="flex items-center gap-1 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3 hover:text-ink"
        >
          {copied ? (
            <Check className="h-3 w-3 text-verified" aria-hidden />
          ) : (
            <Copy className="h-3 w-3" aria-hidden />
          )}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-2 font-mono text-[9px] leading-4 text-ink-2">{code}</pre>
    </div>
  );
}

export function ConfigView({ config, apiKey, onOpenWebhook }: Props) {
  const origin = window.location.origin;
  const wsOrigin = origin.replace(/^http/, "ws");
  const maskedKey = apiKey || "<tenant key>";

  const [channelData, setChannelData] = useState<ChannelConfig | null>(null);
  const [channelChoice, setChannelChoice] = useState<ChannelChoice>("BOTH");
  const [omnichannelStrategy, setOmnichannelStrategy] = useState<OmnichannelStrategy>("WHATSAPP_FIRST");
  const [twilioAccountSid, setTwilioAccountSid] = useState("");
  const [twilioAuthToken, setTwilioAuthToken] = useState("");
  const [twilioFromNumber, setTwilioFromNumber] = useState("");
  const [whatsappProvider, setWhatsappProvider] = useState<WhatsAppProvider>("META");
  const [whatsappPhoneNumberId, setWhatsappPhoneNumberId] = useState("");
  const [whatsappAccessToken, setWhatsappAccessToken] = useState("");
  const [whatsappWabaId, setWhatsappWabaId] = useState("");

  const [savingChannels, setSavingChannels] = useState(false);
  const [channelSaveSuccess, setChannelSaveSuccess] = useState<string | null>(null);
  const [channelSaveError, setChannelSaveError] = useState<string | null>(null);

  const [testingTwilio, setTestingTwilio] = useState(false);
  const [twilioTestResult, setTwilioTestResult] = useState<TestTwilioResponse | null>(null);

  const [testingWhatsApp, setTestingWhatsApp] = useState(false);
  const [whatsAppTestResult, setWhatsAppTestResult] = useState<TestWhatsAppResponse | null>(null);

  useEffect(() => {
    let active = true;
    void api.getChannelConfig().then((cfg) => {
      if (!active) return;
      setChannelData(cfg);
      setChannelChoice(cfg.channel_choice || "BOTH");
      setOmnichannelStrategy(cfg.omnichannel_strategy || "WHATSAPP_FIRST");
      setTwilioAccountSid(cfg.twilio_account_sid || "");
      setTwilioFromNumber(cfg.twilio_from_number || "");
      setWhatsappProvider(cfg.whatsapp_provider || "META");
      setWhatsappPhoneNumberId(cfg.whatsapp_phone_number_id || "");
      setWhatsappWabaId(cfg.whatsapp_waba_id || "");
    }).catch(() => {});
    return () => { active = false; };
  }, []);

  const handleSaveChannels = async () => {
    setSavingChannels(true);
    setChannelSaveSuccess(null);
    setChannelSaveError(null);
    try {
      const updated = await api.updateChannelConfig({
        channel_choice: channelChoice,
        omnichannel_strategy: omnichannelStrategy,
        twilio_account_sid: twilioAccountSid.trim() || null,
        twilio_auth_token: twilioAuthToken.trim() || null,
        twilio_from_number: twilioFromNumber.trim() || null,
        whatsapp_provider: whatsappProvider,
        whatsapp_phone_number_id: whatsappPhoneNumberId.trim() || null,
        whatsapp_access_token: whatsappAccessToken.trim() || null,
        whatsapp_waba_id: whatsappWabaId.trim() || null,
      });
      setChannelData(updated);
      setChannelSaveSuccess("Communication channels and BYOK credentials saved successfully!");
      setTimeout(() => setChannelSaveSuccess(null), 3500);
    } catch (err) {
      setChannelSaveError(err instanceof Error ? err.message : "Failed to save channel configuration.");
    } finally {
      setSavingChannels(false);
    }
  };

  const handleTestTwilio = async () => {
    setTestingTwilio(true);
    setTwilioTestResult(null);
    try {
      const res = await api.testTwilio({
        account_sid: twilioAccountSid.trim() || "mock_sid",
        auth_token: twilioAuthToken.trim() || "mock_token",
        from_number: twilioFromNumber.trim() || "+15551234567",
      });
      setTwilioTestResult(res);
    } catch (err) {
      setTwilioTestResult({
        valid: false,
        message: err instanceof Error ? err.message : "Twilio verification failed",
      });
    } finally {
      setTestingTwilio(false);
    }
  };

  const handleTestWhatsApp = async () => {
    setTestingWhatsApp(true);
    setWhatsAppTestResult(null);
    try {
      const res = await api.testWhatsApp({
        provider: whatsappProvider,
        phone_number_id: whatsappPhoneNumberId.trim() || "mock_phone_id",
        access_token: whatsappAccessToken.trim() || "mock_token",
        waba_id: whatsappWabaId.trim() || null,
        twilio_account_sid: twilioAccountSid.trim() || null,
        twilio_auth_token: twilioAuthToken.trim() || null,
        twilio_from_number: twilioFromNumber.trim() || null,
      });
      setWhatsAppTestResult(res);
    } catch (err) {
      setWhatsAppTestResult({
        valid: false,
        message: err instanceof Error ? err.message : "WhatsApp verification failed",
      });
    } finally {
      setTestingWhatsApp(false);
    }
  };

  const webhookCurl = `curl -X POST ${origin}/api/v1/webhooks/orders \\
  -H "Content-Type: application/json" \\
  -H "X-Tenant-API-Key: ${maskedKey}" \\
  -d '{
    "external_order_id": "ORD-9500",
    "customer_name": "Sana Malik",
    "customer_phone": "0301 234 5678",
    "items_summary": "2x Cotton Kurti",
    "cod_amount": 18000,
    "raw_address": "House 12, Street 4, Block C, Karachi",
    "delivery_window": "Tomorrow 5 PM"
  }'`;

  const wsFrames = `client -> server
{"event": "audio_chunk", "pcm16_base64": "<16 kHz mono PCM16>"}
{"event": "text_utterance", "text": "Yes, deliver after 4 PM"}
{"event": "barge_in"}
{"event": "hangup"}

server -> client
session_ready, transcript_update, tool_trace,
tts_audio, clear_audio, telemetry, call_ended`;

  return (
    <div className="space-y-4">
      {/* Communication Channels & BYOK Telephony Section */}
      <section className="border border-slate-200 bg-white rounded-lg shadow-xs overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 bg-slate-50/70">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-blue-600" />
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-800">
              Communication Channels & BYOK Telephony
            </h2>
          </div>
          <div className="flex items-center gap-2">
            {channelData?.is_whatsapp_verified ? (
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                <CheckCircle2 className="h-3 w-3" /> WhatsApp Live
              </span>
            ) : null}
            {channelData?.is_twilio_verified ? (
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full">
                <CheckCircle2 className="h-3 w-3" /> Twilio Voice Live
              </span>
            ) : null}
            <Button
              size="sm"
              variant="primary"
              onClick={handleSaveChannels}
              disabled={savingChannels}
              className="font-bold flex items-center gap-1.5"
            >
              {savingChannels ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              {savingChannels ? "Saving..." : "Save Channels"}
            </Button>
          </div>
        </div>

        <div className="p-4 space-y-4">
          {channelSaveSuccess ? (
            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded text-xs text-emerald-800 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
              <span>{channelSaveSuccess}</span>
            </div>
          ) : null}

          {channelSaveError ? (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-xs text-red-800 flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-red-600 shrink-0" />
              <span>{channelSaveError}</span>
            </div>
          ) : null}

          {/* Active Channel Selector */}
          <div>
            <label className="block text-xs font-semibold text-slate-800 mb-2">
              Active Verification Channel
            </label>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div
                onClick={() => setChannelChoice("WHATSAPP")}
                className={`p-3 rounded-md border cursor-pointer transition-all ${
                  channelChoice === "WHATSAPP"
                    ? "border-emerald-500 bg-emerald-50/50 shadow-xs ring-1 ring-emerald-500"
                    : "border-slate-200 hover:border-slate-300"
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2 font-bold text-xs text-slate-900">
                    <MessageSquare className="h-4 w-4 text-emerald-600" />
                    WhatsApp Chat Agent
                  </div>
                  {channelChoice === "WHATSAPP" ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> : null}
                </div>
                <p className="text-[11px] text-slate-500 leading-snug">
                  Autonomous conversational agent communicates naturally with buyers via Meta/Twilio WhatsApp.
                </p>
              </div>

              <div
                onClick={() => setChannelChoice("TWILIO")}
                className={`p-3 rounded-md border cursor-pointer transition-all ${
                  channelChoice === "TWILIO"
                    ? "border-blue-500 bg-blue-50/50 shadow-xs ring-1 ring-blue-500"
                    : "border-slate-200 hover:border-slate-300"
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2 font-bold text-xs text-slate-900">
                    <PhoneCall className="h-4 w-4 text-blue-600" />
                    Twilio Voice Phone Calls
                  </div>
                  {channelChoice === "TWILIO" ? <CheckCircle2 className="h-3.5 w-3.5 text-blue-600" /> : null}
                </div>
                <p className="text-[11px] text-slate-500 leading-snug">
                  Autonomous AI voice agent places real phone calls to buyers using Twilio telephony.
                </p>
              </div>

              <div
                onClick={() => setChannelChoice("BOTH")}
                className={`p-3 rounded-md border cursor-pointer transition-all relative ${
                  channelChoice === "BOTH"
                    ? "border-indigo-500 bg-indigo-50/50 shadow-xs ring-1 ring-indigo-500"
                    : "border-slate-200 hover:border-slate-300"
                }`}
              >
                <span className="absolute -top-2 right-2 px-1.5 py-0.2 text-[9px] font-bold uppercase rounded bg-indigo-600 text-white shadow-xs">
                  Recommended
                </span>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2 font-bold text-xs text-slate-900">
                    <Layers className="h-4 w-4 text-indigo-600" />
                    Both (Omnichannel)
                  </div>
                  {channelChoice === "BOTH" ? <CheckCircle2 className="h-3.5 w-3.5 text-indigo-600" /> : null}
                </div>
                <p className="text-[11px] text-slate-500 leading-snug">
                  Smart fallback between WhatsApp chat and voice calling for maximum customer contact rate.
                </p>
              </div>
            </div>
          </div>

          {/* Omnichannel Strategy */}
          {channelChoice === "BOTH" ? (
            <div className="p-3 bg-indigo-50/40 border border-indigo-200 rounded-md">
              <label className="block text-xs font-semibold text-indigo-900 mb-1">
                Omnichannel Fallback Strategy
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1">
                <label className="flex items-start gap-2 p-2 bg-white rounded border border-indigo-100 cursor-pointer">
                  <input
                    type="radio"
                    name="cfgOmniStrategy"
                    value="WHATSAPP_FIRST"
                    checked={omnichannelStrategy === "WHATSAPP_FIRST"}
                    onChange={() => setOmnichannelStrategy("WHATSAPP_FIRST")}
                    className="text-indigo-600 mt-0.5"
                  />
                  <div className="text-xs">
                    <div className="font-semibold text-slate-800">WhatsApp First (Default)</div>
                    <div className="text-[10px] text-slate-500">Initiate WhatsApp chat; trigger Twilio voice call if unread after timeout</div>
                  </div>
                </label>
                <label className="flex items-start gap-2 p-2 bg-white rounded border border-indigo-100 cursor-pointer">
                  <input
                    type="radio"
                    name="cfgOmniStrategy"
                    value="VOICE_FIRST"
                    checked={omnichannelStrategy === "VOICE_FIRST"}
                    onChange={() => setOmnichannelStrategy("VOICE_FIRST")}
                    className="text-indigo-600 mt-0.5"
                  />
                  <div className="text-xs">
                    <div className="font-semibold text-slate-800">Voice First</div>
                    <div className="text-[10px] text-slate-500">Initiate Twilio voice call; send WhatsApp message if customer doesn't pick up</div>
                  </div>
                </label>
              </div>
            </div>
          ) : null}

          {/* Twilio Credentials Box */}
          {(channelChoice === "TWILIO" || channelChoice === "BOTH") ? (
            <div className="p-3.5 border border-blue-200 bg-blue-50/20 rounded-md space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <PhoneCall className="h-4 w-4 text-blue-600" />
                  <span className="text-xs font-bold text-slate-800">Twilio Voice Provider Credentials</span>
                </div>
                <span className="text-[10px] text-slate-500 bg-white px-2 py-0.5 rounded border border-slate-200">
                  BYOK Credentials
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="block text-[11px] font-medium text-slate-700 mb-1">
                    Twilio Account SID
                  </label>
                  <input
                    type="text"
                    value={twilioAccountSid}
                    onChange={(e) => setTwilioAccountSid(e.target.value)}
                    placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxx"
                    className={INPUT_CLASS}
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-700 mb-1">
                    Twilio Auth Token
                  </label>
                  <input
                    type="password"
                    value={twilioAuthToken}
                    onChange={(e) => setTwilioAuthToken(e.target.value)}
                    placeholder={channelData?.twilio_auth_token ? "(Stored - enter to update)" : "Auth Token"}
                    className={INPUT_CLASS}
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-700 mb-1">
                    Twilio From Phone Number
                  </label>
                  <input
                    type="text"
                    value={twilioFromNumber}
                    onChange={(e) => setTwilioFromNumber(e.target.value)}
                    placeholder="+1xxxxxxxxxx"
                    className={INPUT_CLASS}
                  />
                </div>
              </div>

              <div className="flex items-center justify-between pt-1">
                <div className="text-[11px]">
                  {twilioTestResult ? (
                    <span className={`flex items-center gap-1 font-medium ${twilioTestResult.valid ? "text-emerald-700" : "text-red-700"}`}>
                      {twilioTestResult.valid ? <Check className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
                      {twilioTestResult.message}
                    </span>
                  ) : (
                    <span className="text-slate-500">Test live Twilio credentials</span>
                  )}
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={handleTestTwilio}
                  disabled={testingTwilio}
                  className="bg-white border-blue-200 text-blue-700 hover:bg-blue-50"
                >
                  {testingTwilio ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                  {testingTwilio ? "Verifying..." : "Test Twilio Connection"}
                </Button>
              </div>
            </div>
          ) : null}

          {/* WhatsApp Credentials Box */}
          {(channelChoice === "WHATSAPP" || channelChoice === "BOTH") ? (
            <div className="p-3.5 border border-emerald-200 bg-emerald-50/20 rounded-md space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <MessageSquare className="h-4 w-4 text-emerald-600" />
                  <span className="text-xs font-bold text-slate-800">WhatsApp Business API Credentials</span>
                </div>
                <select
                  value={whatsappProvider}
                  onChange={(e) => setWhatsappProvider(e.target.value as WhatsAppProvider)}
                  className={`${SELECT_CLASS} text-xs py-0.5`}
                >
                  <option value="META">Meta Cloud API (Official)</option>
                  <option value="TWILIO">Twilio WhatsApp</option>
                </select>
              </div>

              {whatsappProvider === "META" ? (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[11px] font-medium text-slate-700 mb-1">
                      Meta Phone Number ID
                    </label>
                    <input
                      type="text"
                      value={whatsappPhoneNumberId}
                      onChange={(e) => setWhatsappPhoneNumberId(e.target.value)}
                      placeholder="e.g. 10482910482910"
                      className={INPUT_CLASS}
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-slate-700 mb-1">
                      System User Access Token
                    </label>
                    <input
                      type="password"
                      value={whatsappAccessToken}
                      onChange={(e) => setWhatsappAccessToken(e.target.value)}
                      placeholder={channelData?.whatsapp_access_token ? "(Stored - enter to update)" : "EAAxxxxxxxx..."}
                      className={INPUT_CLASS}
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-slate-700 mb-1">
                      WABA Account ID
                    </label>
                    <input
                      type="text"
                      value={whatsappWabaId}
                      onChange={(e) => setWhatsappWabaId(e.target.value)}
                      placeholder="Optional WABA ID"
                      className={INPUT_CLASS}
                    />
                  </div>
                </div>
              ) : (
                <p className="text-xs text-slate-600">
                  Twilio WhatsApp uses your Twilio Account SID, Auth Token, and From Number configured above (e.g. <code>whatsapp:+14155238886</code>).
                </p>
              )}

              <div className="flex items-center justify-between pt-1">
                <div className="text-[11px]">
                  {whatsAppTestResult ? (
                    <span className={`flex items-center gap-1 font-medium ${whatsAppTestResult.valid ? "text-emerald-700" : "text-red-700"}`}>
                      {whatsAppTestResult.valid ? <Check className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
                      {whatsAppTestResult.message}
                    </span>
                  ) : (
                    <span className="text-slate-500">Test live Meta WhatsApp credentials</span>
                  )}
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={handleTestWhatsApp}
                  disabled={testingWhatsApp}
                  className="bg-white border-emerald-200 text-emerald-700 hover:bg-emerald-50"
                >
                  {testingWhatsApp ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                  {testingWhatsApp ? "Verifying..." : "Test WhatsApp Connection"}
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      </section>

      <div className="grid gap-3 xl:grid-cols-2">
      <Card title="Tenant runtime" icon={KeyRound}>
        <Row label="Merchant" value={config?.tenant.name ?? "-"} />
        <Row label="Tenant id" value={config?.tenant.id ?? "-"} />
        <Row label="Language" value={config?.tenant.default_language ?? "-"} />
        <Row label="Voice persona" value={config?.tenant.voice_persona ?? "-"} />
        <Row
          label="Auto approve COD"
          value={
            config
              ? `PKR ${config.tenant.max_auto_approve_cod.toLocaleString("en-US")}`
              : "-"
          }
        />
        <Row label="Environment" value={config?.environment ?? "-"} />
        <Row
          label="Runtime key"
          value={
            <span className={config?.mock_mode ? "text-warning" : "text-verified"}>
              {config?.mock_mode ? "mock mode" : "groq live"}
            </span>
          }
        />
      </Card>

      <Card title="Model routing" icon={Cpu}>
        <Row label="STT" value={config?.stt_model ?? "-"} />
        <Row label="STT language" value={config?.stt_language ?? "-"} />
        <Row label="LLM" value={config?.llm_model ?? "-"} />
        <Row label="Fast LLM" value={config?.fast_llm_model ?? "-"} />
        <Row label="TTS" value={config?.tts_model ?? "-"} />
        <Row label="Voice" value={config?.tts_default_voice ?? "-"} />
        <Row label="Temperature" value={config?.llm_temperature ?? "-"} />
      </Card>

      <Card title="Voice pipeline" icon={Radio}>
        <Row label="Transport" value="Browser PCM16, 16 kHz mono" />
        <Row label="Frame size" value="320 samples | 20 ms" />
        <Row label="Orpheus chunk cap" value="200 characters" />
        <Row label="Barge-in" value="3 speech frames | 450 ms silence" />
        <Row
          label="Reconnect grace"
          value={
            config ? `${Math.round(config.call_reconnect_grace_seconds)} seconds` : "-"
          }
        />
        <Row label="Turn budget" value="650 ms total" />
        <p className="border-t border-line pt-2 text-[10px] leading-4 text-ink-3">
          TTS WAV chunks stream in order. A client barge-in or RMS VAD trigger flushes queued
          audio immediately and discards any reply still generating.
        </p>
      </Card>

      <Card title="WebSocket wire protocol" icon={Server}>
        <Row label="Endpoint" value={`${wsOrigin}/ws/call/{session_id}`} />
        <Row label="Auth" value="?api_key=<tenant key>" />
        <CodeBlock code={wsFrames} label="Frames" />
      </Card>

      <Card title="Webhook ingestion" icon={Webhook}>
        <Row label="Endpoint" value={`POST ${origin}/api/v1/webhooks/orders`} />
        <Row label="Header" value="X-Tenant-API-Key" />
        <Row label="Payment" value="COD only" />
        <CodeBlock code={webhookCurl} label="curl example" />
        <div className="flex justify-end pt-1">
          <Button size="sm" variant="primary" onClick={onOpenWebhook}>
            Open webhook simulator
            <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
          </Button>
        </div>
      </Card>

      <Card title="Safety invariants" icon={ShieldCheck}>
        <Row label="Tenant isolation" value="every query filters tenant_id" />
        <Row label="Approval gate" value="database owned pause state" />
        <Row label="Approval tools" value="price change | address reroute" />
        <Row label="High value COD" value="above tenant threshold pauses" />
        <Row label="Secrets" value="key stays in browser storage" />
        <p className="border-t border-line pt-2 text-[10px] leading-4 text-ink-3">
          The console never receives the Groq key. It only holds the tenant API key used for
          REST and WebSocket authentication.
        </p>
      </Card>
    </div>
  </div>
  );
}
