import {
  ArrowUpRight,
  Check,
  Copy,
  Cpu,
  KeyRound,
  Radio,
  Server,
  ShieldCheck,
  Webhook,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";

import type { RuntimeConfig } from "../types";
import { Button, SectionLabel } from "./ui";

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
  );
}
