# Implementation Tasks & Execution Checklist

Coding agents must execute these phases sequentially. Mark each item `[x]` only after its verification step passes.

---

## Phase 1: Backend Foundation, Async DB, & Order Ingestion
- [x] **Task 1.1:** Create `backend/requirements.txt` (`fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `aiosqlite`, `asyncpg`, `pydantic>=2.7`, `groq>=0.11.0`, `httpx`, `python-multipart`, `pytest`, `pytest-asyncio`) and `backend/app/config.py` with environment settings (`GROQ_API_KEY`, `DATABASE_URL` defaulting to `sqlite+aiosqlite:///./vanguard_cod.db` for zero-setup local dev and PostgreSQL compatible for prod).
- [x] **Task 1.2:** Implement `backend/app/db/models.py` (`Tenant`, `Order`, `CallSession`, `ApprovalRequest`) and `backend/app/db/session.py` with async engine initialization and startup seed data (1 default tenant + 4 realistic Karachi/Lahore COD orders with varying address quality).
- [x] **Task 1.3:** Implement `backend/app/services/rto_scorer.py` computing the deterministic RTO risk score ($0\text{--}100$) and identifying missing address components.
- [x] **Task 1.4:** Build `backend/app/api/orders.py` and `backend/app/api/webhooks.py` (`POST /api/v1/webhooks/orders`, `GET /api/v1/orders`).
  - *Verification:* Run `pytest backend/tests/test_orders.py` to confirm webhook ingestion and RTO score calculation.
  - *Result:* 10 tests passing on 2026-11-18, including seeded risk scores 33/45/84/70, webhook session queueing, duplicate rejection, and tenant isolation.

---

## Phase 2: Framework-less AsyncGroq Runtime & HITL Tools
- [x] **Task 2.1:** Build `backend/app/agents/runtime.py` containing `ToolTrace`, `AgentStepTrace`, `ToolRegistry`, and `AutonomousVoiceAgent` using `AsyncGroq` (`llama-3.3-70b-versatile`), parallel `asyncio.gather` tool execution, and automatic fallback when `GROQ_API_KEY` is in mock/test mode.
- [x] **Task 2.2:** Implement `backend/app/agents/tools.py` with strict Pydantic v2 schemas for:
  - `confirm_cod_order`
  - `cancel_cod_order`
  - `request_price_or_city_modification` (`requires_approval=True`)
  - `lookup_order_by_phone_or_ref`
  - `log_rider_delivery_attempt`
  - `reschedule_delivery_window`
  - `request_address_reroute` (`requires_approval=True`)
- [x] **Task 2.3:** Implement `backend/app/agents/outbound_verifier.py` and `backend/app/agents/inbound_rescue.py` with concise phone-optimized system prompts.
- [x] **Task 2.4:** Implement `backend/app/api/approvals.py` (`GET /api/v1/approvals`, `POST /api/v1/approvals/{id}/resolve`) so paused agent mutations can be approved or rejected and immediately applied to the database.
  - *Verification:* Run `pytest backend/tests/test_agent_runtime.py` to verify parallel tool execution and HITL approval pausing.
  - *Result:* 12 tests passing on 2026-11-18; the full suite runs 22 tests green (`22 passed`).

---

## Phase 3: Groq Voice Pipeline (Whisper STT, Orpheus TTS Chunker, & VAD)
- [x] **Task 3.1:** Implement `backend/app/voice/stt_groq.py` wrapping `AsyncGroq.audio.transcriptions.create(model="whisper-large-v3-turbo")` with in-memory WAV header framing for raw $16\text{ kHz}$ PCM bytes and millisecond latency measurement.
- [x] **Task 3.2:** Implement `backend/app/voice/tts_provider.py` featuring:
  - `split_into_orpheus_chunks(text: str, max_len: int = 200) -> list[str]` that splits sentences cleanly without ever exceeding $200\text{ characters}$.
  - `synthesize_speech(text: str, voice: str)` calling Groq's `canopylabs/orpheus-v1-english` (`response_format="wav"`).
- [x] **Task 3.3:** Implement `backend/app/voice/vad.py` to compute RMS energy on incoming PCM16 frames and trigger barge-in interruption events.
  - *Verification:* Run `pytest backend/tests/test_voice_pipeline.py` to verify the $\le 200\text{-character}$ chunker invariant and RMS energy detector.
  - *Result:* 13 tests passing on 2026-11-19. Covers sentence and clause splitting, hard-splitting a 450-character word into `200/200/50`, in-memory WAV framing with `RIFF/WAVE` headers and 20 ms duration, RMS silence versus loud frames, 3-frame barge-in while the agent speaks, 450 ms silence finalization, forced finalization with `truncated=True` at the max utterance cap, mock Whisper latency and `language` reporting, and mock Orpheus WAV chunk streaming.

---

## Phase 4: Dual-Mode WebSocket Telephony Router
- [x] **Task 4.1:** Implement `backend/app/api/ws_call.py` (`/ws/call/{session_id}`) coordinating:
  - Initial greeting synthesis when an `OUTBOUND_VERIFY` call connects.
  - Bi-directional handling of `audio_chunk`, `text_utterance`, and `barge_in` events.
  - Real-time emission of `transcript_update`, `tool_trace`, `tts_audio`, `clear_audio`, and `telemetry` packets.
- [x] **Task 4.2:** Wire `backend/app/main.py` with CORS, lifespan DB initialization, and all REST + WebSocket routers.
  - *Verification:* Connect to `/ws/call/{session_id}` using FastAPI `TestClient` and verify full turn execution.
  - *Result:* 15 WebSocket and controller tests passing on 2026-11-19, including full outbound text turn to `confirm_cod_order`, TTS WAV streaming, raw PCM16 utterance transcription, explicit `barge_in` to `clear_audio` (RMS-triggered barge-in is covered in the voice suite), inbound rescue greeting, ping and malformed-frame handling, tenant rejection (`4401`), unknown session rejection (`4404`), terminal session rejection (`4409`), disconnect keeping the call resumable, reconnect skipping the greeting, agent-failure isolation, barge-in during reply generation, barge-in stopping a slow TTS stream, and turns not blocking `ping`. Full backend suite: `54 passed`.

---

## Phase 5: Frontend Operational Console & Browser Softphone Simulator

> Interim simulator available at `GET /softphone`. Production console served by FastAPI at `GET /console` when built (`frontend/dist`).

- [x] **Task 5.1:** Initialize `frontend/` with Vite, React, TypeScript, Tailwind CSS, and Lucide icons configured to the `docs/DESIGN_SYSTEM.md` Obsidian Operational Telemetry palette.
- [x] **Task 5.2:** Build `OrderQueueTable.tsx` and `WebhookSimulatorModal.tsx` to inspect COD orders, view RTO risk bars, inject new test orders, and trigger outbound verification calls with one click.
- [x] **Task 5.3:** Build `SoftphoneDialer.tsx` and `LiveCallMonitor.tsx` supporting:
  - Mode 1: Outbound Verification Call Receiver (simulated customer phone with microphone WebAudio capture + quick-reply voice utterance buttons + barge-in interrupt button).
  - Mode 2: Inbound Delivery Rescue Dialer (act as courier rider or customer calling in).
  - Live HTML5 Canvas audio waveform + real-time `AgentStepTrace` & millisecond latency breakdown panel.
- [x] **Task 5.4:** Build `ApprovalDrawer.tsx` to inspect and approve/reject paused HITL tool requests in real time.
- [x] **Task 5.5:** Decoupled Architecture & Multi-Tenant Self-Serve Store Registration:
  - Decouple the VanguardCOD SaaS Merchant Portal (`/console`) and the Standalone Customer Phone Simulator (`/phone` or `phone-simulator/`).
  - Build self-serve store registration and sign-up flow (`POST /api/v1/auth/register`) generating unique tenant API keys (`vcod_...`) and webhook endpoints for Shopify/WooCommerce.
  - Implement standalone customer smartphone handset simulator in `phone-simulator/` with real-time incoming call listener on `GET /api/v1/calls/pending-outbound`, WebAudio phone ringer synthesis, Answer/Decline call handlers, dual waveform audio visualization, quick customer replies, and text utterance fallback.
  - Add dedicated `SessionsView.tsx` in VanguardCOD SaaS console for call session auditing, turn counts, and sub-second latency analytics.
  - *Verification:* Both `phone-simulator/` and `frontend/` compile with TypeScript `tsc --noEmit` and build cleanly in Vite (`dist/`). Backend mounts `/console` and `/phone` routes. Full pytest suite passes (`62 passed in 8.42s`). Live endpoints verified with simulated store registration, order webhook ingestion, and cross-tenant call ringing on standalone phone handset without tenant headers.
  - *Result:* 62 tests passing on 2026-11-20. Complete decoupling of merchant SaaS portal and customer handset simulator with multi-tenant cross-store ringing achieved.
- [x] **Task 5.6:** Ringing Timeout, Automated Retry Scheduling & Missed Call Handling:
  - Implement 25-second telephony ring timeout on customer softphone simulator with animated countdown progress bar.
  - Add backend `POST /api/v1/calls/{session_id}/timeout`: completes session, increments `order.call_attempts`, and schedules next retry in 2 hours (`order.next_retry_at = utcnow() + 2 hours`, status `PENDING_RETRY`). When reaching `max_call_attempts` (default 3), transitions order to `FAILED_CONTACT`.
  - Add `POST /api/v1/calls/retry-order/{order_id}` and `POST /api/v1/calls/dispatch-retries`: allows instant manual retry from merchant portal / softphone and batch automated dispatch of due retries.
  - Build "Missed Call (No Answer)" screen on standalone customer phone handset displaying store caller ID, order details, attempt progress, and 2-hour retry schedule with fast-forward test trigger.
  - Update merchant SaaS portal `OrderQueueTable.tsx` with retry status badges, "Retry Now" action button, and "Dispatch Retries" header toolbar action.
  - *Verification:* Run `pytest backend/tests/test_console_api.py` covering timeout, 2-hour schedule, fast-forward retry, and max attempt transition to `FAILED_CONTACT`. Full backend suite passes (`63 passed in 14.30s`). `npm.cmd run build` passes on both `frontend` and `phone-simulator`.
  - *Result:* 63 tests passing on 2026-11-20. Production-grade timeout and automated retry scheduling operational across backend and both frontends.

## Phase 6: Omni-Channel Telephony & WhatsApp Cloud API Verification Engine

- [x] **Task 6.1:** Meta WhatsApp Cloud API Webhook Handshake & Ingestion:
  - Implement `GET /api/v1/whatsapp/webhook` with `hub.mode`, `hub.challenge`, and `hub.verify_token` validation.
  - Implement `POST /api/v1/whatsapp/webhook` payload parser extracting incoming message text, customer phone, and message ID.
  - Add phone number normalization to E.164 format without leading `+` for Meta Cloud API compatibility.

- [x] **Task 6.2:** Conversational WhatsApp AI Agent Runner:
  - Implement `backend/app/services/whatsapp_agent.py` using `llama-3.3-70b-versatile` over `AsyncGroq`.
  - Support multi-turn text verification, landmark capture, preferred delivery window scheduling, and cancellation flows.
  - Inject active order context, store identity, and delivery rules into the conversational prompt.

- [x] **Task 6.3:** Twilio Voice PSTN Gateway Integration:
  - Implement `/api/v1/telephony/twilio/voice` endpoint generating dynamic TwiML with `<Gather>` and `<Say>` / `<Play>`.
  - Implement `/api/v1/telephony/twilio/status` callback handler capturing call outcomes (`completed`, `no-answer`, `busy`, `failed`) and triggering 2-hour retry scheduling.

- [x] **Task 6.4:** Multi-Channel Provider Configuration & Store Settings:
  - Add channel preference configuration (`VOICE_ONLY`, `WHATSAPP_ONLY`, `VOICE_THEN_WHATSAPP`) on tenant registration and store settings.
  - Implement credential validation endpoints (`POST /api/v1/channels/test-twilio`, `POST /api/v1/channels/test-whatsapp`).

- [x] **Task 6.5:** Real-Time WhatsApp Human-In-The-Loop Resolution Notification & Anti-Loop Deduplication:
  - Implement `notify_customer_approval_resolution()` in `whatsapp_agent.py` hooked into `POST /api/v1/approvals/{id}/resolve`.
  - On approval rejection: immediately notify customer over WhatsApp with operator note and prompt to confirm original order or cancel.
  - On approval approval: notify customer that the requested modification was accepted.
  - Anti-Loop Session Resumption: preserve and resume call sessions in both `ACTIVE` and `PAUSED_APPROVAL` states.
  - Hold message handling: when customer messages while approval is pending, send hold message without invoking tools or creating duplicate tickets.
  - Approval history prompt injection: inject all past and pending approvals into LLaMA 3.3 prompt with strict negative constraints against repeating rejected requests.
  - Flexible tool arguments: make `new_address` and `requested_cod_amount` optional in `RequestPriceOrCityModificationArgs` and `_handle_price_or_city`.
  - Runtime completion fault tolerance: wrap LLM completion in `_chat()` with try/except fallback.
  - *Verification:* `test_channels_and_omnichannel.py` (8 tests) verifies full WhatsApp approval cycle, rejection notification in transcript, hold handling, and anti-loop deduplication. Full backend test suite: **71 passed**. Frontend builds cleanly with zero errors.



