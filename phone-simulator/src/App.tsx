import {
  Bell,
  BellOff,
  Clock,
  Mic,
  MicOff,
  Phone,
  PhoneCall,
  PhoneForwarded,
  PhoneIncoming,
  PhoneMissed,
  PhoneOff,
  Radio,
  RotateCcw,
  Send,
  Smartphone,
  Sparkles,
  Volume2,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { CallAudioEngine, pcm16ToBase64 } from "./audio";
import type {
  ActiveCall,
  CallerRole,
  CallPhase,
  CallTimeoutResponse,
  CallTrigger,
  Order,
  Telemetry,
  ToolTraceEntry,
  TranscriptEntry,
  TranscriptRole,
} from "./types";

const QUICK_REPLIES = [
  "Yes, please confirm the order and deliver it tomorrow evening.",
  "Deliver after 6 PM near Masjid-e-Tooba, please.",
  "The price of 20,000 is too high. Can you give it to me for 15,000 instead?",
  "I want to cancel this order, I ordered by mistake.",
];

function formatMoney(amount: number): string {
  return "PKR " + Math.round(amount).toLocaleString();
}

function formatClock(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function formatDuration(startMs: number, nowMs: number): string {
  const totalSec = Math.max(0, Math.floor((nowMs - startMs) / 1000));
  const mins = Math.floor(totalSec / 60);
  const secs = totalSec % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

const RING_TIMEOUT_SECONDS = 25;

interface MissedCallInfo {
  storeName: string;
  order: Order | null;
  attempts: number;
  maxAttempts: number;
  nextRetryAt: string | null;
}

export default function App() {
  const demoMode = (() => {
    try {
      return new URLSearchParams(window.location.search).get("demo");
    } catch {
      return null;
    }
  })();

  const [orders, setOrders] = useState<Order[]>([]);
  const [pendingCall, setPendingCall] = useState<CallTrigger | null>(() => {
    if (demoMode === "ringing") {
      return {
        session_id: "demo-sess-1",
        ws_url: "ws://127.0.0.1:8100/ws/call/demo-sess-1",
        direction: "OUTBOUND_VERIFY",
        status: "ACTIVE",
        store_name: "Karachi Threads & Textiles",
        order: {
          id: "ord-101",
          tenant_id: "02c10353-c749-403f-8568-d57f3077ffd3",
          external_order_id: "ORD-9421",
          customer_name: "Ayesha Malik",
          customer_phone: "+92 300 1234567",
          items_summary: "Khaadi Stitched Kurti (M, Maroon) x 1",
          cod_amount: 4500,
          raw_address: "House 42-B, Street 9, DHA Phase 5, Lahore",
          verified_landmark: null,
          delivery_window: null,
          rto_risk_score: 18,
          status: "CALLING",
          call_attempts: 1,
          max_call_attempts: 3,
          created_at: new Date().toISOString(),
        },
      };
    }
    return null;
  });
  const [dismissedSessions, setDismissedSessions] = useState<Set<string>>(new Set());
  const [typedText, setTypedText] = useState("");
  const [inboundOrderId, setInboundOrderId] = useState<string>("");
  const [callerRole, setCallerRole] = useState<CallerRole>("customer");
  const [showTelemetry, setShowTelemetry] = useState(true);
  const [soundEnabled, setSoundEnabled] = useState(false);

  // Call & Timeout state
  const [phase, setPhase] = useState<CallPhase>(() => {
    if (demoMode === "in_call") return "live";
    if (demoMode === "missed") return "missed";
    return "idle";
  });
  const [ringSeconds, setRingSeconds] = useState(() => (demoMode === "ringing" ? 8 : 0));
  const [missedInfo, setMissedInfo] = useState<MissedCallInfo | null>(() => {
    if (demoMode === "missed") {
      return {
        storeName: "Karachi Threads & Textiles",
        order: {
          id: "ord-101",
          tenant_id: "02c10353-c749-403f-8568-d57f3077ffd3",
          external_order_id: "ORD-9421",
          customer_name: "Ayesha Malik",
          customer_phone: "+92 300 1234567",
          items_summary: "Khaadi Stitched Kurti (M, Maroon)",
          cod_amount: 4500,
          raw_address: "House 42-B, Street 9, DHA Phase 5, Lahore",
          verified_landmark: null,
          delivery_window: null,
          rto_risk_score: 18,
          status: "PENDING_RETRY",
          call_attempts: 1,
          max_call_attempts: 3,
          next_retry_at: new Date(Date.now() + 7200000).toISOString(),
          created_at: new Date().toISOString(),
        },
        attempts: 1,
        maxAttempts: 3,
        nextRetryAt: new Date(Date.now() + 7200000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
    }
    return null;
  });
  const [retryingFast, setRetryingFast] = useState(false);
  const [activeCall, setActiveCall] = useState<ActiveCall | null>(() => {
    if (demoMode === "in_call") {
      return {
        sessionId: "demo-sess-1",
        wsUrl: "ws://127.0.0.1:8100/ws/call/demo-sess-1",
        direction: "OUTBOUND_VERIFY",
        startedAt: Date.now() - 32000,
        order: {
          id: "ord-101",
          tenant_id: "02c10353-c749-403f-8568-d57f3077ffd3",
          external_order_id: "ORD-9421",
          customer_name: "Ayesha Malik",
          customer_phone: "+92 300 1234567",
          items_summary: "Khaadi Stitched Kurti (M, Maroon) x 1",
          cod_amount: 4500,
          raw_address: "House 42-B, Street 9, DHA Phase 5, Lahore",
          verified_landmark: "Opposite Jamia Masjid Taqwa",
          delivery_window: "Tomorrow after 6:00 PM",
          rto_risk_score: 18,
          status: "CALLING",
          call_attempts: 1,
          max_call_attempts: 3,
          created_at: new Date().toISOString(),
        },
      };
    }
    return null;
  });
  const [transcript, setTranscript] = useState<TranscriptEntry[]>(() => {
    if (demoMode === "in_call") {
      return [
        {
          id: "t-1",
          role: "assistant",
          text: "Assalam-o-Alaikum Ayesha, calling from Karachi Threads to verify your Cash-on-Delivery order of PKR 4,500.",
          at: Date.now() - 25000,
        },
        {
          id: "t-2",
          role: "user",
          text: "Walaikum Assalam, yes I confirm this order.",
          at: Date.now() - 18000,
        },
        {
          id: "t-3",
          role: "assistant",
          text: "Understood! Could you give us a nearby landmark so our courier finds your location quickly?",
          at: Date.now() - 10000,
        },
        {
          id: "t-4",
          role: "user",
          text: "Deliver right opposite Jamia Masjid Taqwa, green main gate.",
          at: Date.now() - 4000,
        },
        {
          id: "t-5",
          role: "assistant",
          text: "Noted: opposite Jamia Masjid Taqwa. When would you prefer the delivery?",
          at: Date.now() - 1000,
        },
      ];
    }
    return [];
  });
  const [traces, setTraces] = useState<ToolTraceEntry[]>(() => {
    if (demoMode === "in_call") {
      return [
        {
          id: "tr-1",
          step: 1,
          tool_name: "record_delivery_landmark",
          arguments: { landmark: "Opposite Jamia Masjid Taqwa, green main gate" },
          duration_ms: 124,
          status: "success",
          at: Date.now() - 3000,
        },
      ];
    }
    return [];
  });
  const [telemetry, setTelemetry] = useState<Telemetry | null>(() => {
    if (demoMode === "in_call") {
      return {
        stt_ms: 162,
        llm_ms: 235,
        tts_ms: 110,
        total_ms: 507,
      };
    }
    return null;
  });
  const [muted, setMuted] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const wsRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<CallAudioEngine | null>(null);
  const ringerAudioRef = useRef<AudioContext | null>(null);
  const ringerIntervalRef = useRef<number | null>(null);
  const transcriptScrollRef = useRef<HTMLDivElement | null>(null);

  // Load orders for inbound dialer
  useEffect(() => {
    let active = true;
    fetch("/api/v1/orders?limit=50")
      .then((res) => (res.ok ? res.json() : []))
      .then((data: Order[]) => {
        if (active) {
          setOrders(data);
          if (data.length > 0 && !inboundOrderId) setInboundOrderId(data[0].id);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [inboundOrderId]);

  // Clock tick
  useEffect(() => {
    const handle = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(handle);
  }, []);

  // WebAudio Phone Ringer synthesizer
  const playRingChime = useCallback(() => {
    if (!soundEnabled) return;
    try {
      const Context = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = ringerAudioRef.current || new Context();
      ringerAudioRef.current = ctx;
      if (ctx.state === "suspended") void ctx.resume();

      const osc1 = ctx.createOscillator();
      const osc2 = ctx.createOscillator();
      const gain = ctx.createGain();

      osc1.type = "sine";
      osc2.type = "sine";
      osc1.frequency.setValueAtTime(440, ctx.currentTime);
      osc2.frequency.setValueAtTime(480, ctx.currentTime);

      gain.gain.setValueAtTime(0, ctx.currentTime);
      gain.gain.linearRampToValueAtTime(0.12, ctx.currentTime + 0.05);
      gain.gain.linearRampToValueAtTime(0.12, ctx.currentTime + 1.2);
      gain.gain.linearRampToValueAtTime(0, ctx.currentTime + 1.3);

      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(ctx.destination);

      osc1.start(ctx.currentTime);
      osc2.start(ctx.currentTime);
      osc1.stop(ctx.currentTime + 1.3);
      osc2.stop(ctx.currentTime + 1.3);
    } catch {
      // Audio autoplay policy ignored
    }
  }, [soundEnabled]);

  const stopRinger = useCallback(() => {
    if (ringerIntervalRef.current) {
      window.clearInterval(ringerIntervalRef.current);
      ringerIntervalRef.current = null;
    }
  }, []);

  // Poll for pending outbound calls
  useEffect(() => {
    if (phase === "live" || phase === "connecting") {
      stopRinger();
      return;
    }

    const poll = async () => {
      try {
        const res = await fetch("/api/v1/calls/pending-outbound");
        if (!res.ok) return;
        const pendingList = (await res.json()) as CallTrigger[];
        const available = pendingList.find(
          (p) => !dismissedSessions.has(p.session_id) && p.session_id !== activeCall?.sessionId,
        );
        if (available) {
          if (!pendingCall || pendingCall.session_id !== available.session_id) {
            setPendingCall(available);
            playRingChime();
            if (!ringerIntervalRef.current) {
              ringerIntervalRef.current = window.setInterval(playRingChime, 3000);
            }
          }
        } else {
          setPendingCall(null);
          stopRinger();
        }
      } catch {
        // Ignored
      }
    };

    void poll();
    const handle = window.setInterval(poll, 2500);
    return () => {
      window.clearInterval(handle);
      stopRinger();
    };
  }, [activeCall?.sessionId, dismissedSessions, pendingCall, phase, playRingChime, stopRinger]);

  // Auto-scroll transcript
  useEffect(() => {
    if (transcriptScrollRef.current) {
      transcriptScrollRef.current.scrollTop = transcriptScrollRef.current.scrollHeight;
    }
  }, [transcript]);

  const stopAllSpeech = useCallback(() => {
    if (typeof window !== "undefined" && window.speechSynthesis) {
      try {
        window.speechSynthesis.cancel();
      } catch {}
    }
    audioRef.current?.stopPlayback();
    audioRef.current?.setAgentSpeaking(false);
  }, []);

  const speakAssistantDialogue = useCallback(
    (text: string) => {
      if (!soundEnabled || typeof window === "undefined" || !window.speechSynthesis) return;
      try {
        window.speechSynthesis.cancel();
        const clean = text.replace(/[*_#`]/g, "").trim();
        if (!clean) return;
        const utt = new SpeechSynthesisUtterance(clean);
        utt.rate = 1.0;
        utt.pitch = 1.0;

        const voices = window.speechSynthesis.getVoices();
        const naturalVoice =
          voices.find(
            (v) =>
              v.lang.startsWith("en") &&
              (v.name.includes("Natural") ||
                v.name.includes("Google") ||
                v.name.includes("Samantha") ||
                v.name.includes("Zira") ||
                v.name.includes("David")),
          ) || voices.find((v) => v.lang.startsWith("en"));
        if (naturalVoice) {
          utt.voice = naturalVoice;
        }

        audioRef.current?.setAgentSpeaking(true);
        utt.onend = () => {
          audioRef.current?.setAgentSpeaking(false);
        };
        utt.onerror = () => {
          audioRef.current?.setAgentSpeaking(false);
        };
        window.speechSynthesis.speak(utt);
      } catch {
        audioRef.current?.setAgentSpeaking(false);
      }
    },
    [soundEnabled],
  );

  // Audio & WebSocket Handlers
  const closeCall = useCallback(() => {
    stopAllSpeech();
    if (activeCall?.sessionId) {
      setDismissedSessions((prev) => new Set(prev).add(activeCall.sessionId));
    }
    if (wsRef.current) {
      try {
        wsRef.current.close(1000, "hangup");
      } catch {}
      wsRef.current = null;
    }
    audioRef.current?.stopPlayback();
    audioRef.current = null;
    setPhase("ended");
    setMuted(false);
  }, [activeCall?.sessionId, stopAllSpeech]);

  const connectWebSocket = useCallback(
    async (trigger: CallTrigger) => {
      stopRinger();
      stopAllSpeech();
      setPhase("connecting");
      setTranscript([]);
      setTraces([]);
      setTelemetry(null);

      setActiveCall({
        sessionId: trigger.session_id,
        wsUrl: trigger.ws_url,
        direction: trigger.direction,
        order: trigger.order,
        startedAt: Date.now(),
      });

      // Init WebAudio
      const audio = new CallAudioEngine();
      audioRef.current = audio;

      try {
        await audio.startMic((pcm) => {
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(
              JSON.stringify({
                event: "audio_chunk",
                pcm16_base64: pcm16ToBase64(pcm),
              }),
            );
          }
        });
      } catch (micErr) {
        console.warn("Mic unavailable, text mode available:", micErr);
      }

      // Init WebSocket
      const ws = new WebSocket(trigger.ws_url);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const frame = JSON.parse(event.data);
          const type = frame.event || "";

          if (type === "session_ready") {
            setPhase("live");
          } else if (type === "transcript_update") {
            const role = (frame.role || "system") as TranscriptRole;
            const text = String(frame.text || "");
            if (text.trim()) {
              setTranscript((prev) => [
                ...prev,
                { id: `msg-${Date.now()}-${prev.length}`, role, text, at: Date.now() },
              ]);
              if (role === "assistant") {
                speakAssistantDialogue(text);
              }
            }
          } else if (type === "tts_audio" && frame.wav_base64) {
            // If Orpheus returns long real audio and speech synthesis is disabled
            if (frame.wav_base64.length > 8000 && !window.speechSynthesis) {
              audioRef.current?.enqueueWav(frame.wav_base64);
            }
          } else if (type === "clear_audio") {
            stopAllSpeech();
          } else if (type === "telemetry") {
            setTelemetry({
              stt_ms: Number(frame.stt_ms || 0),
              llm_ms: Number(frame.llm_ms || 0),
              tts_ms: Number(frame.tts_ms || 0),
              total_ms: Number(frame.total_ms || 0),
            });
          } else if (type === "tool_trace") {
            setTraces((prev) => [
              {
                id: `trace-${Date.now()}-${prev.length}`,
                step: Number(frame.step || 0),
                tool_name: frame.tool_name || "tool",
                arguments: frame.arguments || {},
                duration_ms: Number(frame.duration_ms || 0),
                status: frame.status || "UNKNOWN",
                result: frame.result,
                error: frame.error || null,
                approval_id: frame.approval_id || null,
                at: Date.now(),
              },
              ...prev,
            ]);
          } else if (type === "call_ended") {
            closeCall();
          }
        } catch {}
      };

      ws.onclose = () => {
        closeCall();
      };
      ws.onerror = () => {
        setPhase("error");
        closeCall();
      };
    },
    [closeCall, speakAssistantDialogue, stopAllSpeech, stopRinger],
  );

  const handleAnswer = async () => {
    if (!pendingCall) return;
    const target = pendingCall;
    setDismissedSessions((prev) => new Set(prev).add(target.session_id));
    setPendingCall(null);
    await connectWebSocket(target);
  };

  const handleTimeout = useCallback(async () => {
    if (!pendingCall) return;
    const target = pendingCall;
    const targetSessionId = target.session_id;
    stopRinger();
    setDismissedSessions((prev) => new Set(prev).add(targetSessionId));
    setPendingCall(null);
    setRingSeconds(0);
    try {
      const res = await fetch(`/api/v1/calls/${targetSessionId}/timeout`, {
        method: "POST",
      });
      if (res.ok) {
        const data = (await res.json()) as CallTimeoutResponse;
        setMissedInfo({
          storeName: target.store_name || "Online Store",
          order: target.order,
          attempts: data.call_attempts,
          maxAttempts: data.max_call_attempts,
          nextRetryAt: data.next_retry_at,
        });
      } else {
        setMissedInfo({
          storeName: target.store_name || "Online Store",
          order: target.order,
          attempts: (target.order?.call_attempts || 0) + 1,
          maxAttempts: target.order?.max_call_attempts || 3,
          nextRetryAt: new Date(Date.now() + 2 * 3600 * 1000).toISOString(),
        });
      }
    } catch {
      setMissedInfo({
        storeName: target.store_name || "Online Store",
        order: target.order,
        attempts: (target.order?.call_attempts || 0) + 1,
        maxAttempts: target.order?.max_call_attempts || 3,
        nextRetryAt: new Date(Date.now() + 2 * 3600 * 1000).toISOString(),
      });
    }
    setPhase("missed");
  }, [pendingCall, stopRinger]);

  const handleDecline = async () => {
    await handleTimeout();
  };

  const isRinging = Boolean(pendingCall) && phase !== "live" && phase !== "connecting";

  // Ring timeout timer (25s)
  useEffect(() => {
    if (!isRinging || !pendingCall) {
      setRingSeconds(0);
      return;
    }
    const interval = window.setInterval(() => {
      setRingSeconds((prev) => {
        if (prev + 1 >= RING_TIMEOUT_SECONDS) {
          void handleTimeout();
          return RING_TIMEOUT_SECONDS;
        }
        return prev + 1;
      });
    }, 1000);
    return () => window.clearInterval(interval);
  }, [isRinging, pendingCall?.session_id, handleTimeout]);

  const handleSendUtterance = (text: string) => {
    const val = text.trim();
    if (!val || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ event: "text_utterance", text: val }));
    setTypedText("");
  };

  const handleBargeIn = () => {
    stopAllSpeech();
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ event: "barge_in" }));
    }
  };

  const handleToggleMute = () => {
    setMuted((prev) => {
      const next = !prev;
      audioRef.current?.setMuted(next);
      return next;
    });
  };

  const handleHangup = () => {
    stopAllSpeech();
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ event: "hangup" }));
      } catch {}
    }
    closeCall();
  };

  const handleStartInbound = async () => {
    const target = orders.find((o) => o.id === inboundOrderId) || orders[0];
    if (!target) return;
    stopRinger();
    try {
      const res = await fetch("/api/v1/calls/start-inbound", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ order_id: target.id, caller_role: callerRole }),
      });
      if (res.ok) {
        const trigger = (await res.json()) as CallTrigger;
        await connectWebSocket(trigger);
      }
    } catch {}
  };

  const inCall = phase === "live" || phase === "connecting";
  const activeOrder = activeCall?.order ?? pendingCall?.order ?? null;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans select-none">
      {/* Top Application Header */}
      <header className="bg-slate-900 border-b border-slate-800 px-5 py-3.5 flex items-center justify-between z-30 shadow-md">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-500 text-white flex items-center justify-center shadow-md">
            <Smartphone className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm tracking-tight text-white">
                VanguardCOD Customer Phone Simulator
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-950 border border-emerald-800 text-emerald-300">
                4G VoLTE &bull; Pakistan
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Standalone customer handset simulator. Listens for automated COD verification calls from your SaaS store.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setSoundEnabled((p) => !p)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs border border-slate-700 cursor-pointer shadow-xs"
          >
            {soundEnabled ? (
              <>
                <Bell className="h-3.5 w-3.5 text-amber-400" />
                <span className="hidden sm:inline font-medium">Ringer On</span>
              </>
            ) : (
              <>
                <BellOff className="h-3.5 w-3.5 text-slate-500" />
                <span className="hidden sm:inline font-medium">Ringer Muted</span>
              </>
            )}
          </button>

          <button
            type="button"
            onClick={() => setShowTelemetry((p) => !p)}
            className="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs border border-slate-700 cursor-pointer shadow-xs"
          >
            <Radio className="h-3.5 w-3.5 text-blue-400" />
            <span className="font-medium">{showTelemetry ? "Hide AI Telemetry" : "Show AI Telemetry"}</span>
          </button>
        </div>
      </header>

      {/* Main Workspace */}
      <main className="flex-1 p-4 md:p-8 flex items-center justify-center">
        <div className="w-full max-w-6xl grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* PHONE HANDSET CHASSIS */}
          <div className={`${showTelemetry ? "lg:col-span-5" : "lg:col-span-12"} flex justify-center`}>
            <div className="w-[360px] h-[680px] bg-slate-900 rounded-[48px] p-3.5 shadow-2xl border-4 border-slate-700 relative flex flex-col justify-between">
              {/* Hardware side buttons */}
              <div className="absolute -left-[7px] top-28 w-[3px] h-10 bg-slate-700 rounded-l-md" />
              <div className="absolute -left-[7px] top-42 w-[3px] h-10 bg-slate-700 rounded-l-md" />
              <div className="absolute -right-[7px] top-32 w-[3px] h-14 bg-slate-700 rounded-r-md" />

              {/* Screen Bezel */}
              <div className="w-full h-full bg-slate-950 rounded-[38px] overflow-hidden flex flex-col relative text-white border border-slate-800">
                {/* Top Status Bar */}
                <div className="w-full h-8 bg-slate-950 pt-2 px-6 flex items-center justify-between z-20 shrink-0">
                  <span className="text-[11px] font-semibold text-slate-400 font-mono">
                    {formatClock(now)}
                  </span>
                  <div className="w-20 h-4 bg-black rounded-full flex items-center justify-center gap-1.5 border border-slate-800">
                    <span className="h-1.5 w-1.5 rounded-full bg-slate-900 border border-slate-700" />
                    <span className="h-1.5 w-1.5 rounded-full bg-blue-900" />
                  </div>
                  <div className="flex items-center gap-1.5 text-[10px] text-slate-400 font-mono">
                    <span>5G</span>
                    <span>100%</span>
                  </div>
                </div>

                {/* 1. RINGING STATE */}
                {isRinging ? (
                  <div className="flex-1 flex flex-col items-center justify-between p-6 bg-gradient-to-b from-slate-900 via-slate-950 to-slate-950 animate-in fade-in duration-300">
                    <div className="flex flex-col items-center text-center mt-6">
                      <span className="text-[11px] font-semibold uppercase tracking-widest text-emerald-400 animate-pulse flex items-center gap-1.5 mb-2">
                        <PhoneIncoming className="h-3.5 w-3.5" />
                        Incoming Call from Store
                      </span>
                      <h2 className="text-xl font-bold text-white leading-tight">
                        {pendingCall?.store_name || "Online Store"}
                      </h2>
                      <p className="text-xs text-slate-400 mt-1">
                        COD Order Verification Agent
                      </p>
                      <div className="mt-3 px-3.5 py-1 bg-slate-800/80 border border-slate-700 rounded-full text-xs text-emerald-300 font-mono">
                        Order {activeOrder?.external_order_id ?? "New"} &bull;{" "}
                        {formatMoney(activeOrder?.cod_amount ?? 0)}
                      </div>
                      <div className="mt-2 text-center text-[11px] text-slate-300 space-y-0.5">
                        <p>Customer: <strong>{activeOrder?.customer_name ?? "Valued Customer"}</strong></p>
                        {activeOrder?.items_summary ? (
                          <p className="text-[10px] text-slate-400 truncate max-w-[260px]">{activeOrder.items_summary}</p>
                        ) : null}
                      </div>
                    </div>

                    {/* Ringing Avatar */}
                    <div className="relative my-3">
                      <div className="w-20 h-20 rounded-full bg-emerald-500/20 animate-ping absolute inset-0" />
                      <div className="w-20 h-20 rounded-full bg-gradient-to-tr from-emerald-600 to-teal-500 flex items-center justify-center text-white shadow-xl relative z-10">
                        <PhoneCall className="h-8 w-8 animate-bounce" />
                      </div>
                    </div>

                    {/* Ring Timeout Countdown & Progress Bar */}
                    <div className="w-full max-w-[240px] bg-slate-900/90 border border-slate-800 rounded-xl p-2.5 flex flex-col items-center gap-1.5 shadow-inner">
                      <div className="flex items-center justify-between w-full text-[10px] text-slate-400 font-mono">
                        <span className="flex items-center gap-1 text-amber-400 font-medium">
                          <Clock className="h-3 w-3" /> Ringing
                        </span>
                        <span>{Math.max(0, RING_TIMEOUT_SECONDS - ringSeconds)}s remaining</span>
                      </div>
                      <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                        <div
                          className="bg-amber-400 h-full transition-all duration-1000 ease-linear rounded-full"
                          style={{
                            width: `${Math.max(0, Math.min(100, ((RING_TIMEOUT_SECONDS - ringSeconds) / RING_TIMEOUT_SECONDS) * 100))}%`,
                          }}
                        />
                      </div>
                    </div>

                    {/* Controls */}
                    <div className="w-full flex items-center justify-around mb-3">
                      <div className="flex flex-col items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => void handleDecline()}
                          className="w-14 h-14 rounded-full bg-red-600 hover:bg-red-700 text-white flex items-center justify-center shadow-lg transition-transform active:scale-95 cursor-pointer"
                          title="Silence / Ignore (triggers auto-retry schedule)"
                        >
                          <PhoneOff className="h-6 w-6" />
                        </button>
                        <span className="text-[10px] text-slate-400 font-medium">Ignore</span>
                      </div>

                      <div className="flex flex-col items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => void handleAnswer()}
                          className="w-16 h-16 rounded-full bg-emerald-500 hover:bg-emerald-600 text-white flex items-center justify-center shadow-xl animate-pulse transition-transform active:scale-95 cursor-pointer"
                        >
                          <Phone className="h-7 w-7" />
                        </button>
                        <span className="text-[11px] text-emerald-300 font-bold">Answer</span>
                      </div>
                    </div>
                  </div>
                ) : inCall ? (
                  /* 2. ACTIVE IN-CALL STATE */
                  <div className="flex-1 flex flex-col justify-between p-3.5 bg-slate-950 overflow-hidden">
                    {/* Header */}
                    <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                      <div className="flex items-center gap-2">
                        <div className="h-8 w-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold">
                          AI
                        </div>
                        <div>
                          <h3 className="text-xs font-bold text-white">
                            {activeCall?.order?.customer_name ? `${activeCall.order.customer_name}` : "Store Voice Agent"}
                          </h3>
                          <div className="flex items-center gap-1 text-[10px] text-emerald-400 font-mono">
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                            {activeCall?.order?.external_order_id ? `${activeCall.order.external_order_id} • ` : ""}
                            In Call &bull; {activeCall ? formatDuration(activeCall.startedAt, now) : "00:00"}
                          </div>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={handleToggleMute}
                        className={`p-1.5 rounded-full text-xs cursor-pointer ${
                          muted ? "bg-red-500/20 text-red-400" : "bg-slate-800 text-slate-300 hover:text-white"
                        }`}
                      >
                        {muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                      </button>
                    </div>

                    {/* Waveform Bar */}
                    <div className="my-1.5 bg-slate-900/80 rounded-md p-2 border border-slate-800 text-[9px] text-slate-400 font-mono flex items-center justify-between">
                      <span className="flex items-center gap-1 text-cyan-400">
                        <Volume2 className="h-3 w-3" /> Agent Audio Stream
                      </span>
                      <span className="flex items-center gap-1 text-emerald-400">
                        <Mic className="h-3 w-3" /> Microphone Active
                      </span>
                    </div>

                    {/* Transcript Stream */}
                    <div
                      ref={transcriptScrollRef}
                      className="flex-1 overflow-y-auto space-y-2 pr-1 py-1 text-xs"
                    >
                      {transcript.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center text-center text-slate-500 p-4">
                          <Sparkles className="h-6 w-6 text-blue-400 mb-2 animate-pulse" />
                          <p className="text-xs font-medium text-slate-300">Audio connected</p>
                          <p className="text-[10px] text-slate-500 mt-1">
                            Greeting order {activeOrder?.external_order_id}...
                          </p>
                        </div>
                      ) : (
                        transcript.map((msg) => {
                          const isAgent = msg.role === "assistant";
                          const isSystem = msg.role === "system";
                          if (isSystem) {
                            return (
                              <div
                                key={msg.id}
                                className="text-center text-[10px] text-slate-500 font-mono py-1 px-2 bg-slate-900/50 rounded"
                              >
                                {msg.text}
                              </div>
                            );
                          }
                          return (
                            <div
                              key={msg.id}
                              className={`flex flex-col ${isAgent ? "items-start" : "items-end"}`}
                            >
                              <span className="text-[9px] text-slate-500 uppercase tracking-wider mb-0.5 px-1 font-mono">
                                {isAgent ? "Store Agent" : "You (Customer)"}
                              </span>
                              <div
                                className={`p-2.5 rounded-2xl max-w-[85%] text-xs leading-relaxed shadow-sm ${
                                  isAgent
                                    ? "bg-slate-800 text-slate-100 rounded-tl-xs border border-slate-700"
                                    : "bg-emerald-600 text-white rounded-tr-xs"
                                }`}
                              >
                                {msg.text}
                              </div>
                            </div>
                          );
                        })
                      )}
                    </div>

                    {/* Quick Replies & Actions */}
                    <div className="pt-2 border-t border-slate-800 space-y-1.5">
                      <div className="text-[9px] font-semibold text-slate-400 uppercase tracking-wider">
                        Quick Customer Replies (Click to Test):
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {QUICK_REPLIES.map((reply) => (
                          <button
                            key={reply}
                            type="button"
                            onClick={() => handleSendUtterance(reply)}
                            className="text-[10px] bg-slate-800 hover:bg-slate-700 text-slate-200 px-2 py-1 rounded border border-slate-700 truncate max-w-[310px] text-left transition-colors cursor-pointer"
                          >
                            &ldquo;{reply}&rdquo;
                          </button>
                        ))}
                      </div>

                      {/* Utterance Input & Barge In */}
                      <div className="flex items-center gap-1.5 pt-1">
                        <input
                          type="text"
                          value={typedText}
                          onChange={(e) => setTypedText(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleSendUtterance(typedText);
                          }}
                          placeholder="Or type customer response..."
                          className="flex-1 bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
                        />
                        <button
                          type="button"
                          onClick={() => handleSendUtterance(typedText)}
                          disabled={!typedText.trim()}
                          className="p-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 rounded text-white cursor-pointer"
                        >
                          <Send className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={handleBargeIn}
                          className="px-2 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 rounded text-[10px] font-bold cursor-pointer"
                        >
                          Barge In
                        </button>
                      </div>

                      <button
                        type="button"
                        onClick={handleHangup}
                        className="w-full py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white font-bold text-xs flex items-center justify-center gap-1.5 shadow-md transition-colors cursor-pointer"
                      >
                        <PhoneOff className="h-4 w-4" />
                        Hang Up Call
                      </button>
                    </div>
                  </div>
                ) : phase === "missed" ? (
                  /* 3. MISSED CALL (NO ANSWER / TIMEOUT) */
                  <div className="flex-1 flex flex-col justify-between p-5 bg-gradient-to-b from-slate-900 via-slate-950 to-slate-950 animate-in fade-in duration-300">
                    <div className="flex flex-col items-center text-center mt-2">
                      <div className="w-16 h-16 rounded-full bg-red-500/20 border border-red-500/30 flex items-center justify-center text-red-400 mb-2">
                        <PhoneMissed className="h-8 w-8" />
                      </div>
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-red-400 flex items-center gap-1">
                        Missed Call &bull; No Answer
                      </span>
                      <h2 className="text-lg font-bold text-white mt-1">
                        {missedInfo?.storeName || "Online Store"}
                      </h2>
                      <p className="text-[11px] text-slate-400">
                        Autonomous COD Verification Agent
                      </p>
                    </div>

                    {/* Order & Retry Schedule Details Card */}
                    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 space-y-3 shadow-lg text-left">
                      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                        <span className="text-[11px] font-mono font-semibold text-slate-300">
                          Order {missedInfo?.order?.external_order_id ?? "COD"}
                        </span>
                        <span className="text-xs font-mono font-bold text-emerald-400">
                          {formatMoney(missedInfo?.order?.cod_amount ?? 0)}
                        </span>
                      </div>

                      <div className="space-y-1 text-xs">
                        <div className="text-slate-400 text-[11px]">
                          Customer: <span className="text-slate-200 font-semibold">{missedInfo?.order?.customer_name ?? "Valued Customer"}</span>
                        </div>
                        <div className="text-slate-400 text-[11px]">
                          Contact: <span className="text-slate-200 font-mono">{missedInfo?.order?.customer_phone ?? "-"}</span>
                        </div>
                        {missedInfo?.order?.items_summary ? (
                          <div className="text-slate-400 text-[11px] truncate">
                            Items: <span className="text-slate-300">{missedInfo.order.items_summary}</span>
                          </div>
                        ) : null}
                      </div>

                      <div className="pt-2 border-t border-slate-800/80">
                        {missedInfo && missedInfo.attempts < missedInfo.maxAttempts ? (
                          <div className="bg-amber-950/40 border border-amber-800/50 rounded-xl p-3 space-y-1">
                            <div className="flex items-center gap-1.5 text-xs font-bold text-amber-300">
                              <Clock className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                              <span>Retry Attempt {missedInfo.attempts} of {missedInfo.maxAttempts}</span>
                            </div>
                            <p className="text-[11px] text-amber-200/90 leading-tight">
                              Customer did not answer within 25s. Next automated retry scheduled in <strong>2 hours</strong>.
                            </p>
                          </div>
                        ) : (
                          <div className="bg-red-950/40 border border-red-800/50 rounded-xl p-3 space-y-1">
                            <div className="flex items-center gap-1.5 text-xs font-bold text-red-300">
                              <PhoneMissed className="h-3.5 w-3.5 text-red-400 shrink-0" />
                              <span>Failed Contact ({missedInfo?.maxAttempts || 3} calls unanswered)</span>
                            </div>
                            <p className="text-[11px] text-red-200/90 leading-tight">
                              Maximum retry limit reached. Order flagged in SaaS portal for manual review.
                            </p>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="space-y-2 pt-2">
                      {missedInfo?.order ? (
                        <button
                          type="button"
                          disabled={retryingFast}
                          onClick={async () => {
                            if (!missedInfo?.order) return;
                            setRetryingFast(true);
                            try {
                              const res = await fetch(`/api/v1/calls/retry-order/${missedInfo.order.id}`, {
                                method: "POST",
                              });
                              if (res.ok) {
                                setPhase("idle");
                                setMissedInfo(null);
                              }
                            } catch {}
                            finally {
                              setRetryingFast(false);
                            }
                          }}
                          className="w-full py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold text-xs flex items-center justify-center gap-1.5 shadow-md cursor-pointer transition-colors"
                        >
                          <RotateCcw className={`h-3.5 w-3.5 ${retryingFast ? "animate-spin" : ""}`} />
                          {retryingFast ? "Triggering..." : "Simulate Fast-Forward Retry Call Now"}
                        </button>
                      ) : null}

                      <button
                        type="button"
                        onClick={() => {
                          setPhase("idle");
                          setMissedInfo(null);
                        }}
                        className="w-full py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium text-xs flex items-center justify-center cursor-pointer transition-colors"
                      >
                        Dismiss &bull; Return to Standby
                      </button>
                    </div>
                  </div>
                ) : (
                  /* 4. IDLE / DIALER STATE */
                  <div className="flex-1 flex flex-col justify-between p-5 bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950">
                    <div className="flex flex-col items-center text-center mt-4 space-y-1">
                      <div className="text-3xl font-light text-slate-100 font-mono tracking-tight">
                        {formatClock(now)}
                      </div>
                      <div className="text-xs text-slate-400">
                        Karachi &bull; Pakistan Standard Time
                      </div>
                    </div>

                    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 space-y-2 shadow-lg">
                      <div className="flex items-center gap-2 text-xs font-bold text-emerald-400">
                        <Radio className="h-4 w-4 animate-pulse text-emerald-400" />
                        Waiting for Incoming Store Call
                      </div>
                      <p className="text-[11px] text-slate-400 leading-relaxed">
                        When an order is created or when you trigger an AI verification call in the VanguardCOD SaaS portal, this handset will instantly ring.
                      </p>
                      <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-500 font-mono">
                        <span>Listening on /pending-outbound</span>
                        <span className="h-2 w-2 rounded-full bg-emerald-500 animate-ping" />
                      </div>
                    </div>

                    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-3.5 space-y-2.5">
                      <div className="text-[11px] font-bold text-slate-300 flex items-center gap-1.5">
                        <PhoneForwarded className="h-3.5 w-3.5 text-blue-400" />
                        Simulate Inbound Customer Call
                      </div>
                      <p className="text-[10px] text-slate-400">
                        Test delivery rescue when the customer or rider dials the store toll-free number.
                      </p>

                      <div className="space-y-1.5">
                        <select
                          value={inboundOrderId}
                          onChange={(e) => setInboundOrderId(e.target.value)}
                          className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
                        >
                          {orders.map((o) => (
                            <option key={o.id} value={o.id}>
                              {o.external_order_id} &bull; {o.customer_name} ({formatMoney(o.cod_amount)})
                            </option>
                          ))}
                        </select>

                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => setCallerRole("customer")}
                            className={`flex-1 py-1 rounded text-[10px] font-medium border cursor-pointer ${
                              callerRole === "customer"
                                ? "bg-blue-600 text-white border-blue-500"
                                : "bg-slate-800 text-slate-400 border-slate-700"
                            }`}
                          >
                            As Customer
                          </button>
                          <button
                            type="button"
                            onClick={() => setCallerRole("rider")}
                            className={`flex-1 py-1 rounded text-[10px] font-medium border cursor-pointer ${
                              callerRole === "rider"
                                ? "bg-blue-600 text-white border-blue-500"
                                : "bg-slate-800 text-slate-400 border-slate-700"
                            }`}
                          >
                            As Rider
                          </button>
                        </div>

                        <button
                          type="button"
                          onClick={() => void handleStartInbound()}
                          disabled={!orders.length}
                          className="w-full py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white font-bold text-xs flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
                        >
                          <Phone className="h-3.5 w-3.5" />
                          Dial Store Toll-Free Line
                        </button>
                      </div>
                    </div>

                    <div className="text-center text-[10px] text-slate-500">
                      VanguardCOD Telephony Simulator Handset
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* RIGHT COLUMN: LIVE AI TELEMETRY & TOOL EXECUTION TRACES */}
          {showTelemetry ? (
            <div className="lg:col-span-7 space-y-4">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Radio className="h-4 w-4 text-emerald-400 animate-pulse" />
                    <h2 className="text-sm font-bold text-white">
                      Live Telephony Telemetry & Tool Execution Log
                    </h2>
                  </div>
                  <span className="text-[10px] text-slate-400 font-mono">
                    Groq Whisper + Llama 3.3 + Orpheus
                  </span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Real-time sub-second latency breakdown of the AI verification agent as speech chunks stream across the WebSocket telephony bridge.
                </p>

                {/* Telemetry Metrics */}
                <div className="grid grid-cols-4 gap-2 mt-4">
                  <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-[10px] text-slate-500 uppercase font-mono block">STT Latency</span>
                    <span className="text-sm font-bold text-slate-200 font-mono">
                      {telemetry?.stt_ms ? `${Math.round(telemetry.stt_ms)} ms` : "-"}
                    </span>
                  </div>
                  <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-[10px] text-slate-500 uppercase font-mono block">LLM Reasoning</span>
                    <span className="text-sm font-bold text-blue-400 font-mono">
                      {telemetry?.llm_ms ? `${Math.round(telemetry.llm_ms)} ms` : "-"}
                    </span>
                  </div>
                  <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-[10px] text-slate-500 uppercase font-mono block">TTS Synthesis</span>
                    <span className="text-sm font-bold text-amber-400 font-mono">
                      {telemetry?.tts_ms ? `${Math.round(telemetry.tts_ms)} ms` : "-"}
                    </span>
                  </div>
                  <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-[10px] text-slate-500 uppercase font-mono block">Total Turn</span>
                    <span className="text-sm font-bold text-emerald-400 font-mono">
                      {telemetry?.total_ms ? `${Math.round(telemetry.total_ms)} ms` : "-"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Tool Execution Traces */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
                <div className="bg-slate-800/80 px-4 py-2.5 text-xs font-bold text-slate-300 border-b border-slate-800">
                  Agent Tool Execution Traces ({traces.length})
                </div>
                <div className="p-4 space-y-2 max-h-96 overflow-y-auto">
                  {traces.length === 0 ? (
                    <div className="text-center py-8 text-xs text-slate-500">
                      No tool executions in this session yet. Answer a call to see tools execute in real time.
                    </div>
                  ) : (
                    traces.map((t) => (
                      <div
                        key={t.id}
                        className="bg-slate-950 border border-slate-800 rounded-lg p-3 space-y-1.5"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs font-bold text-blue-400">
                            {t.tool_name}()
                          </span>
                          <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-slate-900 border border-slate-700 text-emerald-400">
                            {t.status} &bull; {Math.round(t.duration_ms)} ms
                          </span>
                        </div>
                        {Object.keys(t.arguments).length > 0 ? (
                          <pre className="text-[10px] font-mono text-slate-400 bg-slate-900/60 p-2 rounded overflow-x-auto">
                            {JSON.stringify(t.arguments, null, 2)}
                          </pre>
                        ) : null}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
}
