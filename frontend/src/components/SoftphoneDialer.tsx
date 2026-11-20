import {
  ArrowRight,
  Mic,
  MicOff,
  PhoneCall,
  PhoneOff,
  RotateCcw,
  Zap,
} from "lucide-react";
import { useEffect, useState } from "react";

import type { CallController } from "../hooks/useCallSession";
import type { CallerRole, Order } from "../types";
import { formatMoney, maskUrl, shortId } from "../lib/format";
import { Button, Field, INPUT_CLASS, SectionLabel, SELECT_CLASS } from "./ui";

type Mode = "outbound" | "inbound";

interface Props {
  controller: CallController;
  orders: Order[];
  selectedOrder: Order | null;
  onSelectOrder: (orderId: string) => void;
  onActivity: () => void;
  compact?: boolean;
}

const OUTBOUND_REPLIES = [
  "Yes, please confirm the order and deliver it tomorrow evening.",
  "Please reschedule the delivery to the day after tomorrow.",
  "The address is wrong. Let me give you the correct landmark.",
  "That COD amount is too high. Can you reduce the price?",
];

const INBOUND_CUSTOMER_REPLIES = [
  "I want to confirm the delivery of my COD order.",
  "Please change the delivery address for my order.",
  "Can you deliver after 6 PM instead?",
];

const INBOUND_RIDER_REPLIES = [
  "I am at the customer address but nobody is answering the phone.",
  "The customer refused the parcel. What should I do next?",
  "The address looks wrong. I need a verified landmark.",
];

export function SoftphoneDialer({
  controller,
  orders,
  selectedOrder,
  onSelectOrder,
  onActivity,
  compact = false,
}: Props) {
  const [mode, setMode] = useState<Mode>("outbound");
  const [role, setRole] = useState<CallerRole>("customer");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [showInterrupt, setShowInterrupt] = useState(false);

  const { phase, call, micError, error, notice, connectionLost, muted, interruptedAt } =
    controller;
  const inCall =
    phase === "live" || phase === "connecting" || phase === "reconnecting" || phase === "ending";
  const canTalk = phase === "live";
  const busy = starting || phase === "connecting";

  useEffect(() => {
    if (!interruptedAt) return;
    setShowInterrupt(true);
    const handle = window.setTimeout(() => setShowInterrupt(false), 1400);
    return () => window.clearTimeout(handle);
  }, [interruptedAt]);

  useEffect(() => {
    if (phase === "idle" || phase === "ended" || phase === "error") {
      setStarting(false);
    }
  }, [phase]);

  const start = async () => {
    if (!selectedOrder) {
      setStartError("Select an order first.");
      return;
    }
    setStarting(true);
    setStartError(null);
    try {
      if (mode === "outbound") {
        await controller.startOutbound(selectedOrder);
      } else {
        await controller.startInbound(selectedOrder, role);
      }
      onActivity();
    } catch (startFailure) {
      setStartError(
        startFailure instanceof Error ? startFailure.message : String(startFailure),
      );
    } finally {
      setStarting(false);
    }
  };

  const send = (text: string) => {
    if (controller.sendText(text)) setDraft("");
  };

  const replies =
    mode === "outbound"
      ? OUTBOUND_REPLIES
      : role === "rider"
        ? INBOUND_RIDER_REPLIES
        : INBOUND_CUSTOMER_REPLIES;

  return (
    <section className={`flex flex-col ${compact ? "gap-2.5 p-3" : "gap-3 p-4"}`}>
      <div className="flex items-center justify-between">
        <SectionLabel>Softphone simulator</SectionLabel>
        <span className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              inCall ? "bg-verified animate-pulse" : "bg-ink-3"
            }`}
          />
          {inCall ? "Line active" : "Line idle"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-px border border-line bg-line">
        <button
          type="button"
          onClick={() => setMode("outbound")}
          disabled={inCall}
          aria-pressed={mode === "outbound"}
          className={`px-2 py-1.5 text-[11px] transition-colors disabled:opacity-50 ${
            mode === "outbound" ? "bg-panel-2 text-ink" : "bg-panel text-ink-2 hover:text-ink"
          }`}
        >
          Outbound receiver
        </button>
        <button
          type="button"
          onClick={() => setMode("inbound")}
          disabled={inCall}
          aria-pressed={mode === "inbound"}
          className={`px-2 py-1.5 text-[11px] transition-colors disabled:opacity-50 ${
            mode === "inbound" ? "bg-panel-2 text-ink" : "bg-panel text-ink-2 hover:text-ink"
          }`}
        >
          Inbound dialer
        </button>
      </div>

      <Field label="Order under call">
        <select
          value={selectedOrder?.id ?? ""}
          onChange={(event) => onSelectOrder(event.target.value)}
          disabled={inCall}
          className={SELECT_CLASS}
        >
          <option value="">Select an order</option>
          {orders.map((order) => (
            <option key={order.id} value={order.id}>
              {order.external_order_id} | {order.customer_name} |{" "}
              {formatMoney(order.cod_amount)}
            </option>
          ))}
        </select>
      </Field>

      {mode === "inbound" ? (
        <Field label="Inbound caller role">
          <select
            value={role}
            onChange={(event) => setRole(event.target.value as CallerRole)}
            disabled={inCall}
            className={SELECT_CLASS}
          >
            <option value="customer">Customer calling in</option>
            <option value="rider">Delivery rider calling in</option>
          </select>
        </Field>
      ) : null}

      <div className="grid grid-cols-2 gap-2">
        <Button
          variant="primary"
          onClick={start}
          disabled={!selectedOrder || inCall || busy}
          className="w-full"
        >
          <PhoneCall className="h-3.5 w-3.5" aria-hidden />
          {busy ? "Dialing" : mode === "outbound" ? "Start outbound" : "Start inbound"}
        </Button>
        <Button
          variant="danger"
          onClick={controller.hangup}
          disabled={!inCall}
          className="w-full"
        >
          <PhoneOff className="h-3.5 w-3.5" aria-hidden />
          Hang up
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Button
          size="sm"
          variant={muted ? "primary" : "outline"}
          onClick={controller.toggleMute}
          disabled={!canTalk}
          aria-pressed={muted}
        >
          {muted ? (
            <MicOff className="h-3.5 w-3.5" aria-hidden />
          ) : (
            <Mic className="h-3.5 w-3.5" aria-hidden />
          )}
          {muted ? "Unmute" : "Mute"}
        </Button>
        <Button
          size="sm"
          onClick={controller.bargeIn}
          disabled={!canTalk}
          title="Send barge-in and stop agent audio immediately"
        >
          <Zap className="h-3.5 w-3.5" aria-hidden />
          Interrupt
        </Button>
        {connectionLost ? (
          <Button size="sm" variant="primary" onClick={controller.reconnect}>
            <RotateCcw className="h-3.5 w-3.5" aria-hidden />
            Reconnect
          </Button>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            onClick={controller.clear}
            disabled={inCall}
            title="Reset the call monitor"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden />
            Clear
          </Button>
        )}
      </div>

      {showInterrupt ? (
        <div className="border border-critical/40 bg-critical/10 px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.08em] text-critical">
          Barge-in sent. Agent audio stopped.
        </div>
      ) : null}

      {micError ? (
        <div className="border border-warning/40 bg-warning/10 px-2.5 py-2 text-[11px] leading-4 text-warning">
          Microphone unavailable: {micError}. Use the text injection input below.
        </div>
      ) : null}

      {connectionLost ? (
        <div className="border border-warning/40 bg-warning/10 px-2.5 py-2 text-[11px] leading-4 text-warning">
          Socket dropped. Reconnect within the grace window to resume this session.
        </div>
      ) : null}

      {notice ? (
        <div className="border border-line bg-panel-2 px-2.5 py-2 text-[11px] leading-4 text-ink-2">
          {notice}
        </div>
      ) : null}

      {error ? (
        <div className="border border-critical/40 bg-critical/10 px-2.5 py-2 text-[11px] leading-4 text-critical">
          {error}
        </div>
      ) : null}

      {startError ? (
        <div className="border border-critical/40 bg-critical/10 px-2.5 py-2 text-[11px] leading-4 text-critical">
          {startError}
        </div>
      ) : null}

      <div className="border border-line bg-panel-2/60 px-2.5 py-2">
        <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
          <div>
            Session
            <div className="mt-0.5 truncate text-[10px] normal-case tracking-normal text-ink-2">
              {call ? shortId(call.sessionId) : "-"}
            </div>
          </div>
          <div>
            Direction
            <div className="mt-0.5 text-[10px] normal-case tracking-normal text-ink-2">
              {call ? call.direction.replaceAll("_", " ").toLowerCase() : "-"}
            </div>
          </div>
          <div className="col-span-2">
            WebSocket
            <div className="mt-0.5 truncate text-[10px] normal-case tracking-normal text-ink-2">
              {call ? maskUrl(call.wsUrl) : "-"}
            </div>
          </div>
          <div>
            Resumed
            <div className="mt-0.5 text-[10px] normal-case tracking-normal text-ink-2">
              {controller.resumed ? "yes" : "no"}
            </div>
          </div>
          <div>
            Mic
            <div className="mt-0.5 text-[10px] normal-case tracking-normal text-ink-2">
              {micError ? "unavailable" : inCall ? (muted ? "muted" : "live") : "idle"}
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <SectionLabel>Text injection</SectionLabel>
        <div className="flex gap-1.5">
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && canTalk) send(draft);
            }}
            placeholder={canTalk ? "Type a caller utterance" : "Start a call to inject text"}
            disabled={!canTalk}
            className={INPUT_CLASS}
            aria-label="Caller utterance input"
          />
          <Button
            variant="primary"
            size="sm"
            onClick={() => send(draft)}
            disabled={!canTalk || !draft.trim()}
            aria-label="Send caller utterance"
          >
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {replies.map((reply) => (
            <button
              key={reply}
              type="button"
              disabled={!canTalk}
              onClick={() => send(reply)}
              className="border border-line bg-panel-2 px-2 py-1 text-left text-[10px] leading-4 text-ink-2 transition-colors hover:border-ink-3/40 hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
            >
              {reply}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
