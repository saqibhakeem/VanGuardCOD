import { useEffect, useRef } from "react";

import type { CallController } from "../hooks/useCallSession";
import type { ToolTraceEntry, TranscriptEntry } from "../types";
import {
  formatClock,
  formatDuration,
  formatMs,
  latencyTone,
  shortId,
  TONE_BORDER,
  TONE_TEXT,
} from "../lib/format";
import type { Tone } from "../lib/format";
import { StatusPill } from "./StatusPill";
import { Waveform } from "./Waveform";
import { SectionLabel } from "./ui";

interface Props {
  controller: CallController;
  variant?: "compact" | "full";
}

const PHASE_LABEL: Record<string, string> = {
  idle: "Idle",
  connecting: "Connecting",
  live: "In call",
  ending: "Ending",
  reconnecting: "Reconnecting",
  ended: "Call ended",
  error: "Call error",
};

const PHASE_TONE: Record<string, Tone> = {
  idle: "neutral",
  connecting: "warning",
  live: "verified",
  ending: "warning",
  reconnecting: "warning",
  ended: "neutral",
  error: "critical",
};

function messageTone(role: TranscriptEntry["role"]): string {
  if (role === "assistant") return "border-accent/25 bg-accent/5 text-ink";
  if (role === "user") return "border-verified/25 bg-verified/5 text-ink";
  return "border-line bg-panel-2 font-mono text-[10px] leading-4 text-ink-2";
}

function TraceCard({ trace }: { trace: ToolTraceEntry }) {
  return (
    <details className="border border-line bg-panel-2/70 px-2 py-1.5">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="truncate font-mono text-[11px] text-ink">{trace.tool_name}</span>
          <span className="shrink-0 font-mono text-[9px] text-ink-3">
            {formatMs(trace.duration_ms)}
          </span>
        </span>
        <StatusPill status={trace.status} />
      </summary>
      <div className="mt-1.5 space-y-1.5">
        <pre className="max-h-32 overflow-auto border border-line bg-canvas/60 p-1.5 font-mono text-[9px] leading-4 text-ink-2">
          {JSON.stringify(trace.arguments, null, 2)}
        </pre>
        {trace.result ? (
          <pre className="max-h-24 overflow-auto border border-verified/25 bg-verified/5 p-1.5 font-mono text-[9px] leading-4 text-verified">
            {JSON.stringify(trace.result, null, 2)}
          </pre>
        ) : null}
        {trace.error ? (
          <div className="border border-critical/30 bg-critical/10 p-1.5 font-mono text-[9px] leading-4 text-critical">
            {trace.error}
          </div>
        ) : null}
        {trace.approval_id ? (
          <div className="font-mono text-[9px] text-warning">
            approval {shortId(trace.approval_id)}
          </div>
        ) : null}
      </div>
    </details>
  );
}

function budgetTone(value: number, budget: number): Tone {
  if (value <= 0) return "neutral";
  if (value <= budget) return "verified";
  if (value <= budget * 1.5) return "warning";
  return "critical";
}

export function LiveCallMonitor({ controller, variant = "compact" }: Props) {
  const { phase, call, transcript, traces, telemetry, telemetryHistory, events, now } =
    controller;
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const compact = variant === "compact";
  const tone = PHASE_TONE[phase] ?? "neutral";
  const active = phase === "live" || phase === "connecting" || phase === "reconnecting";

  useEffect(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [transcript.length]);

  const turns = telemetryHistory.length;

  const metrics = telemetry
    ? [
        { label: "STT", value: telemetry.stt_ms, budget: 130 },
        { label: "LLM", value: telemetry.llm_ms, budget: 200 },
        { label: "TTS", value: telemetry.tts_ms, budget: 200 },
        { label: "Total", value: telemetry.total_ms, budget: 650 },
      ]
    : [];

  const transcriptPanel = (
    <div className="flex min-h-0 flex-col border border-line bg-panel">
      <div className="flex items-center justify-between border-b border-line px-2.5 py-1.5">
        <SectionLabel>Live transcript</SectionLabel>
        <span className="font-mono text-[9px] text-ink-3">
          {transcript.length} entries
        </span>
      </div>
      <div
        ref={scrollRef}
        className={`flex flex-col gap-1.5 overflow-y-auto px-2.5 py-2 ${
          compact ? "max-h-56" : "h-[340px]"
        }`}
      >
        {transcript.length === 0 ? (
          <div className="py-6 text-center font-mono text-[10px] text-ink-3">
            No transcript yet.
          </div>
        ) : (
          transcript.map((entry) => (
            <div
              key={entry.id}
              className={`flex max-w-[92%] flex-col gap-0.5 ${
                entry.role === "user" ? "ml-auto items-end" : ""
              } ${entry.role === "system" ? "mx-auto w-full items-center" : ""}`}
            >
              <div className="flex items-center gap-1.5 font-mono text-[8px] uppercase tracking-[0.08em] text-ink-3">
                <span>
                  {entry.role === "assistant"
                    ? "Agent"
                    : entry.role === "user"
                      ? "Caller"
                      : "System"}
                </span>
                <span>{formatClock(entry.at)}</span>
              </div>
              <div
                className={`whitespace-pre-wrap border px-2 py-1.5 text-[11px] leading-4 ${messageTone(entry.role)}`}
              >
                {entry.text}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );

  const tracePanel = (
    <div className="flex min-h-0 flex-col border border-line bg-panel">
      <div className="flex items-center justify-between border-b border-line px-2.5 py-1.5">
        <SectionLabel>Agent execution trace</SectionLabel>
        <span className="font-mono text-[9px] text-ink-3">{traces.length} calls</span>
      </div>
      <div
        className={`flex flex-col gap-1.5 overflow-y-auto px-2.5 py-2 ${
          compact ? "max-h-52" : "h-[280px]"
        }`}
      >
        {traces.length === 0 ? (
          <div className="py-6 text-center font-mono text-[10px] text-ink-3">
            No tool calls yet.
          </div>
        ) : (
          traces.map((trace) => <TraceCard key={trace.id} trace={trace} />)
        )}
      </div>
    </div>
  );

  return (
    <section className={`flex flex-col gap-2.5 ${compact ? "p-3 pt-0" : "p-4"}`}>
      <div className="flex items-center justify-between gap-2">
        <SectionLabel>Live call monitor</SectionLabel>
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.08em] ${TONE_TEXT[tone]} ${TONE_BORDER[tone]}`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                tone === "verified"
                  ? "bg-verified"
                  : tone === "warning"
                    ? "bg-warning animate-pulse"
                    : tone === "critical"
                      ? "bg-critical"
                      : "bg-ink-3"
              }`}
            />
            {PHASE_LABEL[phase]}
          </span>
          <span className="font-mono text-[12px] tabular-nums text-ink">
            {call ? formatDuration(call.startedAt, now) : "00:00"}
          </span>
        </div>
      </div>

      <div className="border border-line bg-panel px-2.5 pb-1 pt-2">
        <div className="flex items-center justify-between font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
          <span className="truncate">
            {call ? `${call.order.external_order_id} | ${call.order.customer_name}` : "No active call"}
          </span>
          <span className="shrink-0">
            {call ? `${shortId(call.sessionId)} | ${turns} turns` : "standby"}
          </span>
        </div>
        <Waveform
          getMicLevels={controller.getMicLevels}
          getAgentLevels={controller.getAgentLevels}
          isAgentActive={controller.isAgentActive}
          interruptedAt={controller.interruptedAt}
          active={active}
          size={compact ? "compact" : "full"}
        />
      </div>

      <div className="grid grid-cols-4 gap-px border border-line bg-line">
        {(metrics.length ? metrics : [
          { label: "STT", value: 0, budget: 130 },
          { label: "LLM", value: 0, budget: 200 },
          { label: "TTS", value: 0, budget: 200 },
          { label: "Total", value: 0, budget: 650 },
        ]).map((metric) => {
          const metricTone = budgetTone(metric.value, metric.budget);
          return (
            <div key={metric.label} className="bg-panel px-2 py-1.5">
              <div className="font-mono text-[8px] uppercase tracking-[0.08em] text-ink-3">
                {metric.label}
              </div>
              <div className={`font-mono text-[12px] tabular-nums ${TONE_TEXT[metricTone]}`}>
                {metric.value > 0 ? Math.round(metric.value) : "-"}
              </div>
              <div className="font-mono text-[8px] text-ink-3">{metric.budget} ms</div>
            </div>
          );
        })}
      </div>

      {!compact ? (
        <div className="grid gap-2.5 lg:grid-cols-2">
          {transcriptPanel}
          <div className="flex flex-col gap-2.5">
            {tracePanel}
            <div className="border border-line bg-panel">
              <div className="flex items-center justify-between border-b border-line px-2.5 py-1.5">
                <SectionLabel>Protocol frames</SectionLabel>
                <span className="font-mono text-[9px] text-ink-3">{events.length} events</span>
              </div>
              <div className="h-[132px] overflow-y-auto px-2.5 py-2 font-mono text-[9px] leading-4">
                {events.length === 0 ? (
                  <div className="py-4 text-center text-ink-3">No frames yet.</div>
                ) : (
                  events.slice(0, 60).map((event) => (
                    <div key={event.id} className="grid grid-cols-[52px_1fr] gap-1.5">
                      <span className="text-ink-3">{formatClock(event.at)}</span>
                      <span className="truncate text-accent">
                        {event.name}
                        {event.detail ? (
                          <span className="text-ink-3"> {event.detail}</span>
                        ) : null}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-2.5">
          {transcriptPanel}
          {tracePanel}
        </div>
      )}

      {!compact && call ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border border-line bg-panel px-2.5 py-1.5 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
          <span>session {call.sessionId}</span>
          <span>direction {call.direction.replaceAll("_", " ").toLowerCase()}</span>
          <span>average {formatMs(controller.telemetry?.total_ms)}</span>
          <span>resumed {controller.resumed ? "yes" : "no"}</span>
        </div>
      ) : null}

      {controller.telemetry && latencyTone(controller.telemetry.total_ms) === "critical" ? (
        <div className="border border-critical/30 bg-critical/10 px-2 py-1.5 font-mono text-[9px] uppercase tracking-[0.08em] text-critical">
          Turn latency above 800 ms budget
        </div>
      ) : null}
    </section>
  );
}
