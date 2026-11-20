# System Architecture & Agent State Machine

## 1. High-Level Topology

```text
+-------------------------------------------------------------------------+
|                    MERCHANT OPERATIONS & SIMULATOR UI                   |
|  [Order Queue]   [WebRTC Softphone Lab]   [Live Trace]   [HITL Drawer]  |
+--------+--------------------+------------------+----------------+-------+
         | REST               | WS Audio/JSON    | WS Telemetry   | REST
         v                    v                  v                v
+-------------------------------------------------------------------------+
|                        FASTAPI ASYNC GATEWAY                            |
|  +-----------------------+   +---------------------------------------+  |
|  | Webhook & Order API   |   | Dual-Mode WebSocket Telephony Bridge  |  |
|  | (RTO Risk Calculator) |   | (Browser PCM16 & Twilio mulaw 8kHz)   |  |
|  +-----------+-----------+   +-------------------+-------------------+  |
|              |                                   |                      |
|              |               +-------------------v-------------------+  |
|              |               | Voice Pipeline & VAD Controller       |  |
|              |               | - RMS Energy Barge-In Detector        |  |
|              |               | - Groq whisper-large-v3-turbo (STT)   |  |
|              |               | - Groq Orpheus 200-char Streamer (TTS)|  |
|              |               +-------------------+-------------------+  |
|              |                                   |                      |
|              v                                   v                      |
|  +-------------------------------------------------------------------+  |
|  |           FRAMEWORK-LESS ASYNCGROQ AGENT RUNTIME                  |  |
|  |  - OutboundVerifierAgent & InboundRescueAgent                     |  |
|  |  - Parallel Tool Executor (asyncio.gather)                        |  |
|  |  - Deterministic HITL Checkpoint Gate                             |  |
|  +-----------------------------------+-------------------------------+  |
+--------------------------------------|----------------------------------+
                                       |
                                       v
+-------------------------------------------------------------------------+
|              POSTGRESQL / SQLITE ASYNC STATE & LEDGER                   |
|     [tenants]      [orders]      [call_sessions]   [approval_requests]  |
+-------------------------------------------------------------------------+
```

---

## 2. Voice Activity Detection (VAD) & Barge-In State Machine
Phone conversations fail when an agent keeps talking while the caller interrupts. The `AudioSessionController` maintains two concurrent async tasks per WebSocket connection:
1. **`inbound_listener_loop`**: Reads incoming `audio_chunk` frames, computes Root Mean Square (RMS) energy:
   $$E_{\text{RMS}} = \sqrt{\frac{1}{N} \sum_{i=1}^{N} x_i^2}$$
   - When $E_{\text{RMS}} > \theta_{\text{speech}}$ for $3$ consecutive $20\text{ ms}$ frames while `is_agent_speaking == True`, it immediately sets `interrupt_event.set()`, cancels the active TTS streaming task, and sends `{"event": "clear_audio"}` to the client so playback stops within $50\text{ ms}$.
   - Speech frames are accumulated into an in-memory buffer until silence ($E_{\text{RMS}} < \theta_{\text{silence}}$) persists for $450\text{ ms}$, triggering `stt_groq.transcribe_pcm_buffer()`.
2. **`outbound_speaker_loop`**: Consumes text from the `AsyncGroq` agent, splits text into clauses $\le 200\text{ characters}$, synthesizes audio chunks via `canopylabs/orpheus-v1-english`, and streams `tts_audio` packets unless `interrupt_event.is_set()`.

---

## 3. Framework-less Agent Execution & Checkpoint Flow
Each call session instantiates `AutonomousVoiceAgent` with a scoped `ToolRegistry`:

```text
[Caller Utterance / Initial Call Connect]
                   |
                   v
      +-------------------------+
      | AsyncGroq Chat Complete |
      | (llama-3.3-70b, temp=0.1|
      +------------+------------+
                   |
         Has tool_calls?
          /           \
        No             Yes
        /               \
       v                 v
[Chunk Text <=200c]  [Inspect Tool Metadata]
       |                 |
       v          requires_approval?
[Stream TTS WAV]     /          \
                   No            Yes
                   /              \
                  v                v
        [asyncio.gather]   [Write ApprovalRequest]
        [Execute Tools]    [Set Session PAUSED]
                 |                 |
                 v                 v
        [Append Tool Msg]  [Speak Hold Message to Caller]
        [Re-invoke Model]  [Await Operator Webhook Resume]
```

---

## 4. Dual Agent Personas & Tool Definitions

### 4.1 Outbound Calling Agent (`OutboundVerifierAgent`)
- **System Prompt Rules:** Keep every spoken response under $2$ short sentences ($30\text{ words}$ max). Never read out raw UUIDs. Confirm order intent first, then capture a specific landmark if `verified_landmark` is empty.
- **Registered Tools:**
  - `confirm_cod_order(order_id: str, verified_landmark: str, delivery_window: str)` -> `requires_approval = False` (unless `cod_amount > tenant.max_auto_approve_cod`).
  - `cancel_cod_order(order_id: str, cancellation_reason: str)` -> `requires_approval = False`.
  - `request_price_or_city_modification(order_id: str, new_address: str, requested_cod_amount: float, reason: str)` -> `requires_approval = True`.

### 4.2 Inbound Voice Agent (`InboundRescueAgent`)
- **System Prompt Rules:** Identify whether the caller is a **Customer** or a **Delivery Rider**. Provide concise, operational answers.
- **Registered Tools:**
  - `lookup_order_by_phone_or_ref(query: str)` -> `requires_approval = False`.
  - `log_rider_delivery_attempt(order_id: str, rider_issue: str, gps_note: str)` -> `requires_approval = False`.
  - `reschedule_delivery_window(order_id: str, new_window: str, updated_landmark: str)` -> `requires_approval = False`.
  - `request_address_reroute(order_id: str, proposed_address: str, caller_role: str)` -> `requires_approval = True`.