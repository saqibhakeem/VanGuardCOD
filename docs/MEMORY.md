# MEMORY.md - Persistent Project Context & Decision Log

> **Instruction for Coding Agents:** Read this file at the start of every session and update it whenever a schema, endpoint, or architectural decision changes.

## 1. Current Project Status
- **Active Phase:** Phase 5 complete (Frontend Operational Console & Browser Softphone Simulator delivered and verified).
- **Last Completed Task:** Phase 5 delivery (Vite + React 19 + TypeScript + Tailwind v4 console, dual-mode softphone simulator, HITL approval gate, webhook simulator, and static mount). Full backend suite: `59 passed` on 2026-11-20.
- **Database Default:** Uses `sqlite+aiosqlite:///./vanguard_cod.db` out of the box so local development and automated tests run without external Docker dependencies, while maintaining $100\%$ SQLAlchemy 2.0 compatibility with `postgresql+asyncpg://`. SQLite engines use `NullPool` so pytest can safely run function-scoped event loops without cross-loop connection reuse.

---

## 2. Key Architectural Decisions (ADRs)

### ADR-001: Custom AsyncGroq Runtime Over LangChain/LangGraph
- **Decision:** Build `AutonomousVoiceAgent` and `ToolRegistry` directly on `AsyncGroq` and `asyncio`.
- **Rationale:** Voice agents have a strict $\le 650\text{ ms}$ turn budget. Removing framework abstraction layers eliminates overhead, makes WebSocket barge-in cancellation deterministic, and showcases first-principles systems engineering.

### ADR-002: Orpheus TTS 200-Character Payload Guard
- **Decision:** Enforce a deterministic sentence/clause chunker (`max_len=200`) in `tts_provider.py` before invoking `canopylabs/orpheus-v1-english`.
- **Rationale:** Groq's Orpheus endpoint rejects payloads over $200\text{ characters}$. Chunking by clause not only prevents HTTP 400 errors but also allows the first sentence's WAV audio to stream to the caller while the second sentence is still synthesizing.

### ADR-003: Dual-Mode WebSocket Input (`audio_chunk` + `text_utterance`)
- **Decision:** The `/ws/call/{session_id}` WebSocket accepts both raw $16\text{ kHz}$ PCM audio chunks (transcribed via `whisper-large-v3-turbo`) and direct `text_utterance` JSON frames.
- **Rationale:** Enables real microphone voice conversations via WebAudio API while also allowing deterministic automated testing and one-click demo utterance simulation when testing without a microphone.

### ADR-004: Deterministic Human-in-the-Loop Gate
- **Decision:** Tools in `ToolRegistry` carry a boolean `requires_approval: bool` flag. When `True` (or when `order.cod_amount > tenant.max_auto_approve_cod`), the runtime intercepts execution before calling the Python function, persists an `ApprovalRequest` row in the database, emits a `PAUSED_FOR_APPROVAL` trace to the UI, and returns a polite hold message to the caller.

### ADR-005: Zero-Key Deterministic Mock Runtime
- **Decision:** `AutonomousVoiceAgent` falls back to `MockGroqClient` when `GROQ_API_KEY` is absent or set to a test/mock value. The mock planner emits real tool calls from the same registry schemas so ingestion, HITL pausing, and approval resolution are testable without network access.
- **Rationale:** CI and portfolio reviewers can exercise every backend path with `pytest` and no paid Groq key, while production simply supplies `GROQ_API_KEY` and receives the real `AsyncGroq` client.

### ADR-006: Database Approval Gate Owns the Pause State
- **Decision:** `DatabaseApprovalGate` is the only component that writes `ApprovalRequest` rows. It sets `call_sessions.status = PAUSED_APPROVAL`, sets `orders.status = NEEDS_APPROVAL` (unless already cancelled), and appends a paused tool trace. `POST /api/v1/approvals/{id}/resolve` rebuilds the same scoped tool registry, executes the paused tool with `bypass_approval=True`, appends a system transcript plus tool trace, and returns the session to `ACTIVE`.
- **Rationale:** Keeps the agent runtime free of database imports and guarantees that no mutation happens before an operator decision. Rebuilding the registry from persisted arguments makes the approval endpoint stateless and safe across worker restarts.

### ADR-007: Tenant Auth Fallback for Local Demo
- **Decision:** `X-Tenant-API-Key` selects the tenant via SHA-256 hash lookup. When the header is absent and `ALLOW_ANONYMOUS_TENANT=true` (default in development), requests resolve to the seeded default tenant; an unknown key always returns `401`.
- **Rationale:** Keeps browser demos and tests trivial while every query still filters by the resolved `tenant_id`. Set `ALLOW_ANONYMOUS_TENANT=false` for production.

### ADR-008: Single-Writer Audio Session Controller
- **Decision:** `AudioSessionController` owns one outbound JSON queue and one asynchronous sender task. Receive, speaker, and agent work never call `websocket.send_json` directly. All database writes inside a call are serialized through one `asyncio.Lock`, and telemetry commits run under `asyncio.shield` so a barge-in cancellation cannot interrupt a transaction.
- **Rationale:** Starlette WebSockets do not support concurrent sends, and SQLAlchemy `AsyncSession` does not support concurrent operations. The single-writer queue and DB lock remove both classes of nondeterministic failure while preserving a non-blocking receive loop for barge-in.

### ADR-009: Browser PCM16 Is the Implemented Telephony Transport
- **Decision:** `/ws/call/{session_id}` implements the TRD browser protocol: base64 PCM16 16 kHz `audio_chunk` frames plus `text_utterance` frames. The controller is transport-agnostic and TTS emits WAV chunks. A Twilio Media Streams adapter (mu-law 8 kHz decode, WAV to mu-law re-encode, `media`/`clear` envelopes) is intentionally deferred because it requires a paid number and credentials that the project does not have.
- **Rationale:** The zero-cost browser softphone covers every demo and test requirement, and keeping the controller ignorant of mu-law prevents Twilio-specific format decisions from leaking into the voice pipeline.

### ADR-010: Reconnect Grace Window and Non-Blocking Turns
- **Decision:** An explicit `hangup` marks the call `COMPLETED`. An unexpected socket disconnect leaves the session `ACTIVE`, records the transcript, and schedules a grace finalizer that sets `COMPLETED` after `CALL_RECONNECT_GRACE_SECONDS` (default 60). A reconnect within the window cancels the finalizer, skips the greeting, and seeds the agent with stored `user`/`assistant` history. Joining a `COMPLETED` or `FAILED` session closes with `4409`. Turns run in detached tasks so the receive loop keeps handling `ping` and `barge_in`; each turn captures an interrupt epoch, and `_shutdown` cancels `_turn_tasks` explicitly because cancelling a chained waiter does not cancel the awaited task.
- **Rationale:** Mobile networks drop sockets mid-call. A grace window preserves context without keeping orphaned connections alive forever, and detached turns keep barge-in responsive without allowing a stale reply to be spoken after an interrupt.

---

## 3. Phase 1 to 4 Build State

### 3.1 Files
- `backend/app/config.py`: env settings, `mock_mode`, CORS, seed toggle.
- `backend/app/db/models.py`: `Tenant`, `Order`, `CallSession`, `ApprovalRequest` plus status constants.
- `backend/app/db/session.py`: async engine/session factory, startup seed, JSON transcript/trace append helpers.
- `backend/app/services/rto_scorer.py`: formula implementation, factor breakdown, missing component detection.
- `backend/app/api/`: `webhooks.py`, `orders.py`, `calls.py`, `approvals.py`, `deps.py`.
- `backend/app/agents/`: `runtime.py`, `tools.py`, `hitl.py`, `outbound_verifier.py`, `inbound_rescue.py`.
- `backend/tests/`: `test_orders.py` (10 tests), `test_agent_runtime.py` (12 tests).

### 3.2 REST Surface Implemented
- `POST /api/v1/webhooks/orders`: validates COD payload, normalizes E.164 phone, scores risk, creates order and queued `OUTBOUND_VERIFY` session, returns `ws_url`.
- `GET /api/v1/orders` and `GET /api/v1/orders/{id}`: tenant-scoped with status/reference/phone filters.
- `POST /api/v1/calls/trigger-outbound/{order_id}`: reuses an existing active outbound session or creates one, sets `CALLING`.
- `POST /api/v1/calls/start-inbound`: resolves order by `order_id` or caller phone, creates `INBOUND_RESCUE`.
- `GET /api/v1/approvals`: pending requests with current order values for the operator diff.
- `POST /api/v1/approvals/{approval_id}/resolve`: applies or rejects the paused mutation, returns order and session snapshots.

### 3.3 Behavioral Notes
- Seeded demo tenant key: `vcod_live_demo_key_2026` from `DEFAULT_TENANT_API_KEY`.
- Seeded risk scores: ORD-9042 = 33, ORD-9043 = 45, ORD-9044 = 84, ORD-9045 = 70.
- `confirm_cod_order` is dynamically gated when the order COD exceeds `max_auto_approve_cod`; price/city modification and address reroute are always gated.
- Rejected approvals restore the order to `PENDING_CALL` without applying the proposed arguments; approved confirmations set `VERIFIED`.
- Agent transcript updates and successful tool traces are persisted by `build_persistence_sink`; paused traces are persisted by `DatabaseApprovalGate` to avoid duplicates.

### 3.4 Phase 3 Voice Pipeline
- `backend/app/voice/audio.py`: `pcm16_to_wav` (in-memory RIFF/WAVE framing), `wav_frame_count`, `pcm16_duration_ms`, `pcm16_silence`.
- `backend/app/voice/stt_groq.py`: `GroqSpeechToText.transcribe_pcm_buffer` wraps `AsyncGroq.audio.transcriptions.create` with `whisper-large-v3-turbo`, defaults `language` to `STT_LANGUAGE` (`en`), returns `TranscriptionResult(text, latency_ms, model, audio_ms, wav_bytes)`, and falls back to `MockTranscriptionClient` when `mock_mode` is active.
- `backend/app/voice/tts_provider.py`: `split_into_orpheus_chunks` splits sentences, then clauses, then words, and hard-splits any single token longer than `max_len`, so every chunk satisfies `len(chunk) <= 200`. `GroqTextToSpeech` exposes `synthesize_speech` and `stream_speech`, calls `canopylabs/orpheus-v1-english` with `response_format="wav"`, and uses `MockSpeechClient` (valid tone WAVs) in mock mode.
- `backend/app/voice/vad.py`: `rms_energy` plus stateful `RmsBargeInDetector`. Speech threshold `500.0`, silence threshold `150.0`, 3 consecutive speech frames trigger barge-in while the agent speaks, and 450 ms of silence finalizes and returns the buffered PCM. Utterances are force-finalized at `max_utterance_ms` (default 30000) with `VadDecision.truncated = True`, which bounds memory and prevents a stuck open microphone from buffering forever.

### 3.5 Phase 4 WebSocket Telephony Bridge
- `backend/app/api/ws_call.py`: `GET` upgrade route `WS /ws/call/{session_id}`. Resolves the tenant from `X-Tenant-API-Key` or `?api_key=`, accepts anonymous demo traffic when `ALLOW_ANONYMOUS_TENANT=true`, loads the tenant-scoped call session and order, chooses `build_outbound_agent` or `build_inbound_agent` (caller role from `?caller_role=` or the stored transcript), seeds agent history from the stored transcript on reconnect, and hands control to `AudioSessionController`.
- `backend/app/voice/session.py`: concurrent receive, speaker, sender, and detached turn tasks. Emits `session_ready` (with `resumed`), `transcript_update`, `tool_trace`, `tts_audio`, `clear_audio`, `telemetry`, plus `stt_result`, `vad_barge_in`, `call_paused`, `approval_hold`, `approval_resolved`, `call_ended`, and `error` diagnostics.
- Close codes: `4401` invalid tenant key, `4404` unknown call session or order, `4409` session already `COMPLETED` or `FAILED`.
- `hangup` marks the session `COMPLETED`, commits, flushes `call_ended`, then closes. An unexpected disconnect leaves the session `ACTIVE`, commits the transcript, and schedules a grace finalizer (`CALL_RECONNECT_GRACE_SECONDS`) that marks it `COMPLETED` if no reconnect arrives. Reconnecting cancels the finalizer and skips the greeting.
- User and assistant transcript entries are persisted from the controller, so `_build_history` has real `user`/`assistant` turns to seed a resumed agent.
- Turn, STT, and TTS failures emit localized `agent_failed`, `stt_failed`, and `tts_failed` events without tearing down the socket. Turns capture an interrupt epoch so a barge-in discards a reply that was still generating.
- `avg_turn_latency_ms` is updated with an incremental mean from turn telemetry (`stt_ms + llm_ms + tts_ms`).
- Agent pause state is reconciled from the database before each turn, so resolving an approval through the REST endpoint resumes a live WebSocket session.
- Ringing: the page polls `GET /api/v1/calls/pending-outbound` every 4 seconds while idle. A queued outbound session with no transcript yet shows an incoming call bar with the customer and order. Answering reuses the returned `ws_url`; declining calls `POST /api/v1/calls/{session_id}/decline`, which marks the session `COMPLETED` and returns the order to `PENDING_CALL`. The watch toggle stops polling and clears the ring.
- Tests: `backend/tests/test_voice_pipeline.py` (13), `backend/tests/test_ws_call.py` (11), `backend/tests/test_voice_session.py` (4). Full suite `54 passed` on 2026-11-19.

### 3.6 Standalone Softphone Simulator
- `backend/app/static/softphone.html`: single-file browser softphone served at `GET /softphone`. It needs no build step and no Twilio. `/docs` does not list it because it is not an HTTP API route in the OpenAPI schema.
- Flow: pick a seeded order, choose outbound verification or inbound rescue, start a call, capture the microphone, and speak to the agent. Audio is captured with `getUserMedia` and a `ScriptProcessorNode`, downsampled to 16 kHz PCM16, split into 20 ms frames, base64 encoded, and sent as `audio_chunk`. Incoming `tts_audio` WAV chunks play sequentially. `clear_audio` stops playback.
- Controls: mute mic (sends silence frames so VAD can finalize), interrupt (`barge_in`), hang up, text utterance input, and quick replies.
- Panels: live transcript, tool traces, STT/LLM/TTS/total telemetry, order context, masked session and WebSocket URLs, and an event log.
- Reconnect: an unexpected socket close shows a reconnect bar. Reconnecting within `CALL_RECONNECT_GRACE_SECONDS` resumes the session and skips the greeting. Close codes `4401`, `4404`, and `4409` show explicit messages.
- This is a simulator: the caller is the browser user, not a real PSTN phone. Real phone numbers still require a provider such as Telnyx, SignalWire, or Plivo.
- Tests: `backend/tests/test_softphone_page.py` (2) covers page serving and absence of a Groq key in markup.

### 3.7 Phase 5 React Operational Console
- `frontend/`: Single-page operational console built with Vite 7, React 19, TypeScript 5.9, Tailwind CSS v4 (`@tailwindcss/vite`), and Lucide icons following the `docs/DESIGN_SYSTEM.md` Obsidian Operational Telemetry palette.
- Layout: Full-viewport 3-zone architecture:
  - Left NavRail: Tenant profile, API key input, live backend health dot, navigation across 4 views, pending approval counter badge, and Groq cost/latency telemetry ticker.
  - Center Workspace: Top KPI strip (Verified COD Volume, RTO Risk Prevented, Mean Turn Latency, Active Voice Sessions) plus the active view (Operations Queue, Softphone Simulator Lab, HITL Approval Gate, or Webhook & Voice Config).
  - Right Inspector: Persistent compact softphone dialer and live call monitor with dual-channel canvas waveform and real-time step traces.
- Components:
  - `OrderQueueTable`: Dense operational table with status filters, search by reference/customer/phone, RTO risk score meters, and one-click outbound call triggering.
  - `WebhookSimulatorModal`: Order injection simulator for testing COD payloads, validating fields, computing RTO risk scores, and queueing verification calls.
  - `SoftphoneDialer`: Dual-mode telephony simulator (Mode 1: Outbound Verification Call Receiver as customer; Mode 2: Inbound Delivery Rescue Dialer as rider or customer) with microphone WebAudio capture, quick-reply buttons, barge-in interrupt, and text utterance input.
  - `LiveCallMonitor`: Real-time session monitoring with dual-channel HTML5 canvas waveform (Caller Input #10B981, Agent Output #06B6D4), live transcript stream, expandable `AgentStepTrace` cards, and turn latency breakdown vs budget (STT 130 ms, LLM 200 ms, TTS 200 ms, Total 650 ms).
  - `ApprovalDrawer` and `ApprovalGate`: Real-time HITL approval gate displaying pending paused tool requests, proposed arguments diff, operator notes, and one-click Approve/Reject actions that resume the active call session.
  - `ConfigView`: Tenant runtime profile, model routing table, and copyable cURL / WebSocket wire protocol snippets.
  - `Waveform`: HTML5 canvas rendering caller input and agent output levels with barge-in flash indicator.
- WebAudio Engine (`frontend/src/lib/audio.ts`): Downsamples microphone audio to 16 kHz mono PCM16, batches 20 ms frames (320 samples), base64-encodes for `audio_chunk` frames, analyzes time-domain levels for canvas visualization, and decodes incoming TTS WAV chunks into a gapless playback queue.
- Reusable Call Hook (`frontend/src/hooks/useCallSession.ts`): Coordinates WebSocket lifecycle, message routing, microphone capture, WAV playback, text injection, barge-in interrupts, reconnection with grace window, and activity callbacks.
- Production Mount: `backend/app/main.py` serves the compiled SPA at `/console/` from `frontend/dist` using Starlette `StaticFiles(html=True)`.
- Backend Support Endpoints:
  - `GET /api/v1/config`: Returns sanitized tenant and model runtime configuration.
  - `GET /api/v1/calls/sessions`: Returns tenant-scoped call session summaries with turn counts and average latency.
- Tests: `backend/tests/test_console_api.py` covers runtime config sanitization, tenant authentication, session summary aggregation, tenant isolation, and `/console/` SPA serving. Full backend suite: `59 passed`.



---

## 4. Environment Variables Reference

The backend loads `backend/.env` first, then a project-root `.env` as fallback, without overriding real OS environment variables. Copy `backend/.env.example` to `backend/.env` and fill values. `.env` is gitignored; never commit real keys.

```ini
GROQ_API_KEY=gsk_your_key_here
DATABASE_URL=sqlite+aiosqlite:///./vanguard_cod.db
DEFAULT_TENANT_API_KEY=vcod_live_demo_key_2026
STT_MODEL=whisper-large-v3-turbo
STT_LANGUAGE=en
LLM_MODEL=llama-3.3-70b-versatile
TTS_MODEL=canopylabs/orpheus-v1-english
TTS_DEFAULT_VOICE=troy
CALL_RECONNECT_GRACE_SECONDS=60
ALLOW_ANONYMOUS_TENANT=true
SEED_ON_STARTUP=true
CORS_ORIGINS=*
```