# MEMORY.md - Persistent Project Context & Decision Log

> **Instruction for Coding Agents:** Read this file at the start of every session and update it whenever a schema, endpoint, or architectural decision changes.

## 1. Current Project Status
- **Active Phase:** Phase 6 complete (Omni-Channel Voice & WhatsApp Engine, Twilio Telephony, Meta Cloud API, Real-Time WhatsApp HITL Rejection Notification, Anti-Loop Deduplication, & Clean Multi-Tenant SaaS Bootstrapping).
- **Last Completed Task:** Real-time WhatsApp customer notification on admin approval resolution (approval or rejection), anti-loop session resumption and deduplication, prompt-injected approval history, and flexible partial modification schema. Full backend suite: `71 passed` on 2026-11-24. Frontend build: clean (Vite 7 + React 19).

- **Database Default:** Uses `sqlite+aiosqlite:///./vanguard_cod.db` out of the box so local development and automated tests run without external Docker dependencies, while maintaining $100\%$ SQLAlchemy 2.0 compatibility with `postgresql+asyncpg://`. SQLite engines use `NullPool` so pytest can safely run function-scoped event loops without cross-loop connection reuse. `SEED_ON_STARTUP=false` ensures clean tenant workspaces on fresh boot.

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

### ADR-011: Standalone Customer Phone Simulator & Self-Serve Store Registration
- **Decision:** Strictly decouple the VanguardCOD B2B E-Commerce SaaS Merchant Portal (`frontend/` or `/console`) and the Customer Phone Simulator (`phone-simulator/` or `/phone`) into two isolated projects and endpoints. The merchant manages orders in their modern SaaS dashboard; clicking "Call Customer" initiates the outbound verification call on the backend, queues it in `GET /api/v1/calls/pending-outbound`, and rings the customer simulator on `/phone` or standalone dev port `5174`. The customer phone simulator runs on its own dedicated project/route, synthesizes an authentic phone ringer with WebAudio, and allows the customer to answer or decline the call, speak via microphone, or trigger quick replies. In addition, new e-commerce merchants can self-register their business via `POST /api/v1/auth/register`, immediately receiving a cryptographically random tenant API key (`vcod_...`), a dedicated webhook ingestion endpoint, and an administrator account.
- **Rationale:** Merging the customer handset into the merchant platform layout violated operational realism and confused user testing. Decoupling them lets the user or reviewer test with realistic separation (merchant SaaS console on one monitor or tab, customer smartphone on another).

### ADR-012: Telephony Ring Timeout, Missed Call Schedule, & Fast-Forward Testing
- **Decision:** Outbound phone calls ring on the customer handset for a standard 25-second window with an animated countdown and progress bar. If unanswered within 25 seconds (or if the customer clicks Silence/Ignore), the handset calls `POST /api/v1/calls/{session_id}/timeout`, which marks the call session `COMPLETED`, increments `order.call_attempts`, transitions the order to `PENDING_RETRY`, and sets `order.next_retry_at = utcnow() + 2 hours`. If `order.call_attempts >= order.max_call_attempts` (default 3), the order transitions to `FAILED_CONTACT`. The customer softphone transitions to a dedicated "Missed Call (No Answer)" screen showing store caller ID, order info, call attempt progress, and the 2-hour schedule. In addition, the merchant SaaS dashboard displays attempt badges (`Attempt 1/3 • Retry in 2h`), provides a manual "Retry Now" button calling `POST /api/v1/calls/retry-order/{order_id}` for fast-forward verification testing without waiting 2 hours in demo mode, and offers a batch "Dispatch Retries" toolbar action (`POST /api/v1/calls/dispatch-retries`).
- **Rationale:** Real telephony does not ring forever; unanswered calls time out to prevent infinite carrier billing and line blocking. Scheduling retries 2 hours later mirrors production logistics operations in Pakistan, while providing fast-forward "Retry Now" buttons gives human operators and evaluators immediate feedback during testing.

### ADR-013: Meta WhatsApp Cloud API Omni-Channel Integration
- **Decision:** Integrate Meta WhatsApp Cloud API as a first-class order verification channel alongside voice telephony. The webhook endpoint `GET /api/v1/whatsapp/webhook` handles Meta verification handshakes (`hub.mode`, `hub.challenge`, `hub.verify_token`), and `POST /api/v1/whatsapp/webhook` processes incoming messages using `whatsapp_agent.py` driven by `llama-3.3-70b-versatile`. Merchants configure channel preference (`VOICE_ONLY`, `WHATSAPP_ONLY`, or `VOICE_THEN_WHATSAPP`) upon registration and in store settings.
- **Rationale:** In target emerging markets (e.g. Pakistan), many customers decline voice calls from unknown numbers but actively reply to WhatsApp messages. Providing omni-channel choice allows merchants to verify customers on their preferred channel.

### ADR-014: Outbound WhatsApp Human-In-The-Loop Notification & Anti-Loop Deduplication
- **Decision:** When an operator resolves an approval via `POST /api/v1/approvals/{id}/resolve`, `notify_customer_approval_resolution()` immediately pushes an outbound WhatsApp message to the customer with the resolution (approved or rejected) and the operator note. Furthermore:
  1. `handle_whatsapp_incoming_message` maintains and resumes sessions across both `ACTIVE` and `PAUSED_APPROVAL` states.
  2. If a customer sends messages while an approval ticket is `PENDING`, the agent returns a polite hold message without invoking LLM tool calls or generating redundant approval tickets.
  3. `build_whatsapp_prompt` injects all pending and resolved approval records into the LLaMA 3.3 system prompt with strict negative constraints: if a modification was rejected, the LLM is prohibited from re-calling `request_price_or_city_modification` and must inform the customer that the previous decision stands.
  4. `DatabaseApprovalGate` deduplicates incoming approval requests for the same order and tool, returning the existing ticket ID.
- **Rationale:** Prevents conversational dead-ends where customers are left waiting indefinitely after an admin rejection, and stops infinite approval ticket creation loops caused by session re-creation or repeated LLM tool calls.

### ADR-015: Twilio Telephony Voice Gateway with Automatic Retry Scheduling
- **Decision:** Implement `/api/v1/telephony/twilio/voice` and `/api/v1/telephony/twilio/status` to handle real PSTN phone calls. Outbound calls that end in `no-answer`, `busy`, or `failed` automatically increment `order.call_attempts`, set `order.status = PENDING_RETRY`, and schedule the next attempt in 2 hours (`order.next_retry_at = utcnow() + 2h`), up to `max_call_attempts`.
- **Rationale:** Ensures real cellular and landline calls match the same production-grade timeout and retry lifecycle as the browser softphone simulator.

### ADR-016: Clean Database Bootstrapping and Flexible Partial Modification Arguments
- **Decision:** Set default `SEED_ON_STARTUP=false` and remove hardcoded mock customer accounts from the login interface. In addition, relax `RequestPriceOrCityModificationArgs` to make `new_address` and `requested_cod_amount` optional (`None` default), updating only specified fields in `_handle_price_or_city`.
- **Rationale:** A multi-tenant SaaS must not pollute new merchant workspaces with old mock customer records. Additionally, real-world customer requests often seek only a price discount (keeping address intact) or only an address correction (keeping COD amount intact); requiring both fields caused Groq schema parsing errors or `NoneType` string formatting crashes.

### ADR-017: HTTPS Reverse Proxy Architecture for Meta Webhooks via Ngrok & Vite Proxy
- **Decision:** Expose the FastAPI backend over secure HTTPS via Ngrok for Meta WhatsApp Cloud API webhooks (which mandate public HTTPS), while configuring the Vite dev server proxy in `frontend/vite.config.ts` to seamlessly route `/api` and `/ws` to the local backend without TLS handshake or socket hang-up errors.
- **Rationale:** Resolves TLS socket termination errors and enables seamless local development and live WhatsApp testing simultaneously.

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

### 3.7 Phase 5 React SaaS Operational Console & Standalone Customer Phone Simulator
- `frontend/`: Modern B2B E-Commerce SaaS operational console built with Vite 7, React 19, TypeScript 5.9, Tailwind CSS v4 (`@tailwindcss/vite`), and Lucide icons following modern SaaS design standards (Linear / Stripe / Supabase inspired).
- Theme: Clean SaaS aesthetic (`#0A0D12` dark background, `#121721` elevated cards, emerald `#10B981` active accents, blue `#3B82F6` primary actions, and clean status semantics).
- Standalone Customer Phone Simulator Project (`phone-simulator/` running on port 5174, or served at `/phone`):
  - Completely separate standalone application in its own root directory `phone-simulator/`.
  - Realistic smartphone device casing with bezel, speaker slit, status bar (5G, battery, clock).
  - Background polling on `GET /api/v1/calls/pending-outbound` with WebAudio phone ringer synthesis.
  - Incoming call screen with store caller ID, animated pulsating ring, green Answer, and red Decline buttons.
  - Active call screen with timer, real-time dual-waveform visualizer, conversational speech bubbles for voice agent and customer, microphone WebAudio toggle, quick-reply voice utterance chips, custom speech input, barge-in interrupt, and end call button.
  - Inbound delivery rescue dialer to test customer or rider calling in.
  - Collapsible real-time AI telemetry panel showing sub-second STT, LLM, TTS latency breakdown and tool traces.
- Multi-Tenant Authentication & Self-Serve Store Registration:
  - `POST /api/v1/auth/login` and `POST /api/v1/auth/register`.
  - Self-serve registration in `LoginView.tsx` allows any new store owner to register their brand, generate a dedicated API key (`vcod_...`), configure verification rules, and get their unique webhook URL.
  - Pre-configured demo roles: `VERIFICATION_OFFICER` (Farhan Ahmed), `LOGISTICS_MANAGER` (Sarah Mansoor), and `SYSTEM_ADMIN` (Tariq Malik).
- VanguardCOD Merchant Console Views (`/console` or port 5173):
  - `SaaSNavbar`: Sleek SaaS header with store profile, active AI engine indicator, user role pill, link to Customer Phone Simulator, and navigation tabs.
  - `OrderQueueTable`: Dense SaaS data table with search, status filters, RTO risk meters, and direct "Call Customer" buttons (triggers call without merging phone into console).
  - `SessionsView`: Dedicated audit log of call sessions, turn counts, and turn latency analytics.
  - `KpiStrip`: SaaS metric cards for Verified Orders, RTO Risk Prevented, Delivery Success Rate, and Mean Turn Latency.
  - `ApprovalGate` and `ApprovalDrawer`: Manager authorization inbox with original vs proposed arguments diff and operator notes.
  - `StoreAndSheetsView`: Store webhook configuration, simulated order generator, and two-way Google Sheets sync view.
  - `ConfigView`: Model parameters, Groq routing, and voice persona settings.
- Tests: `backend/tests/test_console_api.py` covers auth login, store registration, role resolution, runtime config, session summaries, timeout, retry scheduling, and `/console` SPA serving. Full backend suite: `63 passed`.

### 3.8 Phase 6 Omni-Channel Voice, WhatsApp Meta Cloud API, & Anti-Loop HITL Engine
- `backend/app/services/whatsapp_agent.py`: Meta WhatsApp Cloud API agent runner with `llama-3.3-70b-versatile`, system instructions injecting approval history, message formatting, and `notify_customer_approval_resolution()` for instant customer dispatch on admin approval decisions.
- `backend/app/api/webhooks.py`: `GET /api/v1/whatsapp/webhook` verification handshake and `POST /api/v1/whatsapp/webhook` incoming message event ingestion.
- `backend/app/api/telephony.py`: Twilio PSTN voice webhook integration (`/api/v1/telephony/twilio/voice`) with dynamic TwiML generation and call status callbacks (`/api/v1/telephony/twilio/status`) mapping no-answer/busy outcomes to 2-hour retry schedules.
- `backend/app/api/channels.py`: Provider credential validation and channel preference endpoints (`POST /api/v1/channels/test-twilio`, `POST /api/v1/channels/test-whatsapp`).
- `backend/app/agents/hitl.py`: Deduplicated approval request checkpointing preventing repeated tickets for identical order mutations.
- `backend/app/agents/tools.py`: Flexible parameter parsing supporting partial updates (discount-only and address-only) without schema validation failures.
- `backend/app/agents/runtime.py`: Fault-tolerant completion fallback in `_chat()` catching Groq API exceptions and returning courteous customer retries.
- Tests: `backend/tests/test_channels_and_omnichannel.py` (8 tests) covering store registration with channel choices, channel config endpoints, credential validation, Meta webhook handshake, WhatsApp conversational AI flow, Twilio TwiML generation, call status retry handling, and WhatsApp approval resolution with anti-loop deduplication. Full backend suite: `71 passed`.

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
SEED_ON_STARTUP=false
CORS_ORIGINS=*
```