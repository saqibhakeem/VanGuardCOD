import { useCallback, useEffect, useRef, useState } from "react";

import { api, withApiKey } from "../api";
import { CallAudio, pcm16ToBase64 } from "../lib/audio";
import type {
  ActiveCall,
  CallDirection,
  CallPhase,
  CallTrigger,
  CallerRole,
  LogEntry,
  Order,
  Telemetry,
  ToolTraceEntry,
  TranscriptEntry,
  TranscriptRole,
} from "../types";

interface ServerFrame {
  event?: string;
  session_id?: string;
  order?: Order;
  direction?: CallDirection;
  resumed?: boolean;
  role?: TranscriptRole;
  text?: string;
  wav_base64?: string;
  stt_ms?: number;
  llm_ms?: number;
  tts_ms?: number;
  total_ms?: number;
  step?: number;
  tool_name?: string;
  arguments?: Record<string, unknown>;
  duration_ms?: number;
  status?: string;
  tool_call_id?: string;
  approval_id?: string;
  result?: unknown;
  error?: string;
  message?: string;
  code?: string;
  reason?: string;
  approval_ids?: string[];
}

interface Options {
  onActivity?: () => void;
}

let sequence = 0;

function nextId(prefix: string): string {
  sequence += 1;
  return `${prefix}-${sequence}`;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function useCallSession({ onActivity }: Options = {}) {
  const [phase, setPhase] = useState<CallPhase>("idle");
  const [call, setCall] = useState<ActiveCall | null>(null);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [traces, setTraces] = useState<ToolTraceEntry[]>([]);
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [telemetryHistory, setTelemetryHistory] = useState<Telemetry[]>([]);
  const [events, setEvents] = useState<LogEntry[]>([]);
  const [muted, setMuted] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resumed, setResumed] = useState(false);
  const [connectionLost, setConnectionLost] = useState(false);
  const [interruptedAt, setInterruptedAt] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  const wsRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<CallAudio | null>(null);
  const callRef = useRef<ActiveCall | null>(null);
  const phaseRef = useRef<CallPhase>("idle");
  const endTimerRef = useRef<number | null>(null);
  const onActivityRef = useRef(onActivity);

  useEffect(() => {
    onActivityRef.current = onActivity;
  }, [onActivity]);

  const updatePhase = useCallback((value: CallPhase) => {
    phaseRef.current = value;
    setPhase(value);
  }, []);

  const updateCall = useCallback((value: ActiveCall | null) => {
    callRef.current = value;
    setCall(value);
  }, []);

  const logEvent = useCallback((name: string, detail = "") => {
    setEvents((previous) =>
      [
        { id: nextId("evt"), at: Date.now(), name, detail },
        ...previous,
      ].slice(0, 120),
    );
  }, []);

  const appendTranscript = useCallback(
    (role: TranscriptRole, text: string) => {
      const value = text.trim();
      if (!value) return;
      setTranscript((previous) => [
        ...previous,
        { id: nextId("msg"), role, text: value, at: Date.now() },
      ]);
    },
    [],
  );

  const stopAudio = useCallback(() => {
    audioRef.current?.stop();
    audioRef.current = null;
    setMuted(false);
  }, []);

  const closeSocket = useCallback(() => {
    const ws = wsRef.current;
    wsRef.current = null;
    if (!ws) return;
    ws.onmessage = null;
    ws.onerror = null;
    ws.onclose = null;
    try {
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close(1000, "client hangup");
      }
    } catch {
      return;
    }
  }, []);

  const handleClose = useCallback(
    (event: CloseEvent) => {
      wsRef.current = null;
      const explicit = phaseRef.current === "ending";
      stopAudio();
      setConnectionLost(false);
      logEvent("socket.closed", `code ${event.code}`);

      if (explicit) {
        updatePhase("ended");
        onActivityRef.current?.();
        return;
      }
      if (event.code === 4409) {
        updatePhase("ended");
        setError("This call session is already completed or failed.");
        onActivityRef.current?.();
        return;
      }
      if (event.code === 4401) {
        updatePhase("error");
        setError("Tenant authentication was rejected. Check the API key.");
        return;
      }
      if (event.code === 4404) {
        updatePhase("error");
        setError("Call session or order was not found.");
        return;
      }
      if (phaseRef.current === "idle" || phaseRef.current === "ended") return;

      updatePhase("reconnecting");
      setConnectionLost(true);
      onActivityRef.current?.();
    },
    [logEvent, stopAudio, updatePhase],
  );

  const handleFrame = useCallback(
    (frame: ServerFrame) => {
      const type = frame.event ?? "";
      logEvent(type, frame.status ?? frame.code ?? "");

      if (type === "session_ready") {
        const current = callRef.current;
        if (current) {
          const next: ActiveCall = {
            ...current,
            sessionId: frame.session_id ?? current.sessionId,
            order: frame.order ?? current.order,
            direction: frame.direction ?? current.direction,
            resumed: Boolean(frame.resumed),
          };
          updateCall(next);
        }
        setResumed(Boolean(frame.resumed));
        setConnectionLost(false);
        updatePhase("live");
        if (frame.resumed) {
          appendTranscript("system", "Call resumed from the stored transcript. Greeting skipped.");
        }
        onActivityRef.current?.();
        return;
      }

      if (type === "transcript_update") {
        appendTranscript(frame.role ?? "system", frame.text ?? "");
        return;
      }

      if (type === "tts_audio") {
        if (frame.wav_base64) audioRef.current?.enqueueWav(frame.wav_base64);
        return;
      }

      if (type === "clear_audio") {
        audioRef.current?.stopPlayback();
        setInterruptedAt(Date.now());
        return;
      }

      if (type === "telemetry") {
        const entry: Telemetry = {
          stt_ms: Number(frame.stt_ms ?? 0),
          llm_ms: Number(frame.llm_ms ?? 0),
          tts_ms: Number(frame.tts_ms ?? 0),
          total_ms: Number(frame.total_ms ?? 0),
        };
        setTelemetry(entry);
        setTelemetryHistory((previous) => [...previous, entry].slice(-30));
        return;
      }

      if (type === "tool_trace") {
        setTraces((previous) =>
          [
            {
              id:
                frame.tool_call_id && frame.tool_call_id.length > 0
                  ? `${frame.tool_call_id}-${previous.length}`
                  : nextId("trace"),
              step: Number(frame.step ?? 0),
              tool_name: frame.tool_name ?? "tool",
              arguments: frame.arguments ?? {},
              duration_ms: Number(frame.duration_ms ?? 0),
              status: frame.status ?? "UNKNOWN",
              result: frame.result,
              error: frame.error ?? null,
              approval_id: frame.approval_id ?? null,
              at: Date.now(),
            },
            ...previous,
          ].slice(0, 40),
        );
        onActivityRef.current?.();
        return;
      }

      if (type === "vad_barge_in") {
        audioRef.current?.stopPlayback();
        setInterruptedAt(Date.now());
        return;
      }

      if (type === "call_paused" || type === "approval_hold") {
        const ids = Array.isArray(frame.approval_ids) ? frame.approval_ids.join(", ") : "";
        setNotice(ids ? `Operator approval required: ${ids}` : "Operator approval required.");
        onActivityRef.current?.();
        return;
      }

      if (type === "approval_resolved") {
        setNotice("Operator approval resolved. Call resumed.");
        appendTranscript("system", "Operator approval resolved. Call resumed.");
        onActivityRef.current?.();
        return;
      }

      if (type === "call_ended") {
        appendTranscript("system", `Call ended. Reason: ${frame.reason ?? "hangup"}.`);
        setNotice("Call ended.");
        updatePhase("ended");
        stopAudio();
        onActivityRef.current?.();
        return;
      }

      if (type === "error") {
        const message = frame.message ?? frame.code ?? "Unknown backend error.";
        setError(`Backend error: ${message}`);
        return;
      }
    },
    [appendTranscript, logEvent, stopAudio, updateCall, updatePhase],
  );

  const openSocket = useCallback(
    (wsUrl: string) => {
      closeSocket();
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onmessage = (event: MessageEvent<string>) => {
        try {
          handleFrame(JSON.parse(event.data) as ServerFrame);
        } catch {
          logEvent("client.parse_error");
        }
      };
      ws.onclose = (event) => handleClose(event);
      ws.onerror = () => logEvent("socket.error");
    },
    [closeSocket, handleClose, handleFrame, logEvent],
  );

  const prepareAudio = useCallback(async () => {
    stopAudio();
    const audio = new CallAudio();
    audioRef.current = audio;
    setMicError(null);
    try {
      await audio.start((pcm) => {
        const ws = wsRef.current;
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(
            JSON.stringify({
              event: "audio_chunk",
              pcm16_base64: pcm16ToBase64(pcm),
            }),
          );
        }
      });
    } catch (audioError) {
      setMicError(messageOf(audioError));
    }
  }, [stopAudio]);

  const reset = useCallback(() => {
    setTranscript([]);
    setTraces([]);
    setTelemetry(null);
    setTelemetryHistory([]);
    setEvents([]);
    setMicError(null);
    setNotice(null);
    setError(null);
    setResumed(false);
    setConnectionLost(false);
    setInterruptedAt(0);
    setMuted(false);
  }, []);

  const openSession = useCallback(
    async (trigger: CallTrigger) => {
      reset();
      updatePhase("connecting");
      setNow(Date.now());
      updateCall({
        sessionId: trigger.session_id,
        wsUrl: withApiKey(trigger.ws_url),
        direction: trigger.direction,
        order: trigger.order,
        resumed: false,
        startedAt: Date.now(),
      });
      await prepareAudio();
      openSocket(withApiKey(trigger.ws_url));
    },
    [openSocket, prepareAudio, reset, updateCall, updatePhase],
  );

  const startOutbound = useCallback(
    async (order: Order) => {
      try {
        const trigger = await api.triggerOutbound(order.id);
        await openSession(trigger);
        return trigger;
      } catch (startError) {
        setError(messageOf(startError));
        updatePhase("error");
        onActivityRef.current?.();
        throw startError;
      }
    },
    [openSession, updatePhase],
  );

  const startInbound = useCallback(
    async (order: Order, role: CallerRole) => {
      try {
        const trigger = await api.startInbound(order.id, role);
        await openSession(trigger);
        return trigger;
      } catch (startError) {
        setError(messageOf(startError));
        updatePhase("error");
        onActivityRef.current?.();
        throw startError;
      }
    },
    [openSession, updatePhase],
  );

  const answerPending = useCallback(
    async (trigger: CallTrigger) => {
      try {
        await openSession(trigger);
        return trigger;
      } catch (startError) {
        setError(messageOf(startError));
        updatePhase("error");
        onActivityRef.current?.();
        throw startError;
      }
    },
    [openSession, updatePhase],
  );

  const hangup = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      closeSocket();
      stopAudio();
      updatePhase("ended");
      return;
    }
    try {
      ws.send(JSON.stringify({ event: "hangup" }));
    } catch {
      closeSocket();
      stopAudio();
      updatePhase("ended");
      return;
    }
    updatePhase("ending");
    setNotice("Ending call.");
    if (endTimerRef.current) window.clearTimeout(endTimerRef.current);
    endTimerRef.current = window.setTimeout(() => {
      closeSocket();
      stopAudio();
      updatePhase("ended");
    }, 3000);
  }, [closeSocket, stopAudio, updatePhase]);

  const reconnect = useCallback(async () => {
    const current = callRef.current;
    if (!current) return;
    setError(null);
    setConnectionLost(false);
    updatePhase("connecting");
    await prepareAudio();
    openSocket(current.wsUrl);
  }, [openSocket, prepareAudio, updatePhase]);

  const sendText = useCallback((text: string) => {
    const value = text.trim();
    if (!value) return false;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setError("No active WebSocket connection.");
      return false;
    }
    ws.send(JSON.stringify({ event: "text_utterance", text: value }));
    return true;
  }, []);

  const bargeIn = useCallback(() => {
    audioRef.current?.stopPlayback();
    setInterruptedAt(Date.now());
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ event: "barge_in" }));
    }
  }, []);

  const toggleMute = useCallback(() => {
    setMuted((previous) => {
      const next = !previous;
      audioRef.current?.setMuted(next);
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    closeSocket();
    stopAudio();
    updateCall(null);
    updatePhase("idle");
    reset();
  }, [closeSocket, reset, stopAudio, updateCall, updatePhase]);

  const getMicLevels = useCallback(
    (count: number): number[] =>
      audioRef.current?.micLevels(count) ?? new Array<number>(count).fill(0),
    [],
  );

  const getAgentLevels = useCallback(
    (count: number): number[] =>
      audioRef.current?.agentLevels(count) ?? new Array<number>(count).fill(0),
    [],
  );

  const isAgentActive = useCallback(
    (): boolean => audioRef.current?.isAgentActive() ?? false,
    [],
  );

  useEffect(() => {
    if (phase !== "live" && phase !== "connecting" && phase !== "reconnecting") {
      return;
    }
    const handle = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(handle);
  }, [phase]);

  useEffect(() => {
    return () => {
      if (endTimerRef.current) window.clearTimeout(endTimerRef.current);
      closeSocket();
      stopAudio();
    };
  }, [closeSocket, stopAudio]);

  return {
    phase,
    call,
    transcript,
    traces,
    telemetry,
    telemetryHistory,
    events,
    muted,
    micError,
    notice,
    error,
    resumed,
    connectionLost,
    interruptedAt,
    now,
    openSession,
    answerPending,
    startOutbound,
    startInbound,
    hangup,
    reconnect,
    sendText,
    bargeIn,
    toggleMute,
    clear,
    getMicLevels,
    getAgentLevels,
    isAgentActive,
  };
}

export type CallController = ReturnType<typeof useCallSession>;
