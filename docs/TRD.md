# Technical Requirements Document (TRD)

## 1. Technology Stack & Model Specifications

### 1.1 Groq AI Pipeline Models
All AI inference is powered via the official `groq` Python SDK (`AsyncGroq`):
1. **Speech-to-Text (STT):**
   - **Model ID:** `whisper-large-v3-turbo`
   - **Endpoint:** `client.audio.transcriptions.create`
   - **Throughput & Cost:** $216\times$ real-time speed factor, $\$0.04$ per hour of audio.
   - **Format:** Accepts `WAV` ($16\text{ kHz}$ mono PCM wrapped with WAV header) or `WEBM`.
2. **Agent Orchestration & Tool Calling:**
   - **Primary Model ID:** `llama-3.3-70b-versatile` ($128\text{K}$ context, $\sim 394\text{ TPS}$, $\$0.59 / \$0.79$ per $1\text{M}$ tokens).
   - **Fast Utility/Classifier Model ID:** `llama-3.1-8b-instant` ($\sim 840\text{ TPS}$, $\$0.05 / \$0.08$ per $1\text{M}$ tokens) for instant RTO pre-scoring.
   - **Temperature:** $0.1$ for deterministic tool calling and concise phone dialogue.
3. **Text-to-Speech (TTS):**
   - **English Model ID:** `canopylabs/orpheus-v1-english`
   - **Endpoint:** `client.audio.speech.create` (`response_format="wav"`, voices: `troy`, `hannah`, `austin`, `daniel`, `autumn`, `diana`).
   - **Hard API Constraint:** Orpheus enforces a strict $200\text{-character}$ maximum per `input` payload. The TTS service MUST split agent responses on sentence/clause boundaries so every chunk satisfies $\text{len}(\text{chunk}) \le 200$.
   - **Urdu/Multilingual Fallback:** Pluggable `TTSProvider` interface supporting `edge-tts` / Azure neural voices (`ur-PK-UzmaNeural`, `ur-PK-AsadNeural`) when tenant language is set to `ur`.

---

## 2. Latency & RTO Scoring Formulas

### 2.1 Turn Latency Budget
Total turn latency $T_{\text{turn}}$ must satisfy:
$$T_{\text{turn}} = T_{\text{VAD\_finalize}} + T_{\text{STT}} + T_{\text{LLM}} + T_{\text{TTS\_first\_chunk}} \le 650\text{ ms}$$
Where target component budgets are:
- $T_{\text{VAD\_finalize}} = 120\text{ ms}$
- $T_{\text{STT}} \le 130\text{ ms}$
- $T_{\text{LLM}} \le 200\text{ ms}$
- $T_{\text{TTS\_first\_chunk}} \le 200\text{ ms}$

### 2.2 Heuristic RTO Risk Score Formula
Upon order ingestion, initial risk score $R \in [0, 100]$ is calculated deterministically before calling:
$$R = \min\left(100, \max\left(0, 20 + 30 \cdot I_{\text{no\_house\_num}} + 25 \cdot I_{\text{short\_addr}} + 25 \cdot \min\left(1.0, \frac{\text{cod\_amount}}{\text{max\_auto\_approve\_cod}}\right)\right)\right)$$
Where:
- $I_{\text{no\_house\_num}} \in \{0, 1\}$ equals $1$ if `raw_address` contains no digits.
- $I_{\text{short\_addr}} \in \{0, 1\}$ equals $1$ if $\text{len}(\text{raw\_address.split}()) < 5$.

---

## 3. Database Schema (SQLAlchemy 2.0 Async)

### 3.1 `tenants`
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `String(36)` | PK, UUID4 | Unique tenant identifier |
| `name` | `String(120)` | NOT NULL | Merchant store name |
| `api_key_hash` | `String(128)` | UNIQUE, INDEX | SHA-256 hash of `X-Tenant-API-Key` |
| `default_language` | `String(10)` | DEFAULT `'en'` | `'en'` or `'ur'` |
| `voice_persona` | `String(32)` | DEFAULT `'troy'` | Orpheus or Urdu voice ID |
| `max_auto_approve_cod` | `Float` | DEFAULT `25000.0` | Threshold above which edits require human approval |
| `created_at` | `DateTime(tz)` | NOT NULL | UTC creation timestamp |

### 3.2 `orders`
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `String(36)` | PK, UUID4 | Internal order UUID |
| `tenant_id` | `String(36)` | FK(`tenants.id`), INDEX | Owning merchant |
| `external_order_id` | `String(64)` | INDEX | Shopify/WooCommerce order number (e.g., `ORD-9042`) |
| `customer_name` | `String(120)` | NOT NULL | Buyer full name |
| `customer_phone` | `String(32)` | INDEX, NOT NULL | E.164 phone number |
| `items_summary` | `Text` | NOT NULL | Line items description |
| `cod_amount` | `Float` | NOT NULL | Payable cash amount |
| `raw_address` | `Text` | NOT NULL | Checkout shipping address |
| `verified_landmark` | `Text` | NULLABLE | Landmark captured by voice agent |
| `delivery_window` | `String(64)` | NULLABLE | Preferred delivery slot |
| `rto_risk_score` | `Integer` | NOT NULL | $0$ to $100$ score |
| `status` | `String(32)` | INDEX | `PENDING_CALL`, `CALLING`, `VERIFIED`, `CANCELLED`, `RESCHEDULED`, `NEEDS_APPROVAL` |
| `created_at` | `DateTime(tz)` | NOT NULL | UTC creation timestamp |

### 3.3 `call_sessions`
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `String(36)` | PK, UUID4 | Call session UUID |
| `tenant_id` | `String(36)` | FK(`tenants.id`), INDEX | Owning merchant |
| `order_id` | `String(36)` | FK(`orders.id`), INDEX | Linked order |
| `direction` | `String(24)` | NOT NULL | `OUTBOUND_VERIFY` or `INBOUND_RESCUE` |
| `status` | `String(24)` | NOT NULL | `ACTIVE`, `PAUSED_APPROVAL`, `COMPLETED`, `FAILED` |
| `avg_turn_latency_ms` | `Float` | DEFAULT `0.0` | Mean turn latency in milliseconds |
| `transcript` | `JSON` | DEFAULT `[]` | Array of `{role, text, timestamp_ms}` |
| `tool_traces` | `JSON` | DEFAULT `[]` | Array of `ToolTrace` objects with latency and args |
| `created_at` | `DateTime(tz)` | NOT NULL | UTC timestamp |

### 3.4 `approval_requests`
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `String(36)` | PK, UUID4 | Approval request UUID |
| `tenant_id` | `String(36)` | FK(`tenants.id`), INDEX | Owning merchant |
| `order_id` | `String(36)` | FK(`orders.id`), INDEX | Target order |
| `call_session_id` | `String(36)` | FK(`call_sessions.id`) | Originating call |
| `tool_name` | `String(64)` | NOT NULL | Name of paused tool |
| `proposed_arguments` | `JSON` | NOT NULL | Proposed mutation payload |
| `reason` | `Text` | NOT NULL | Explanation for operator |
| `status` | `String(24)` | DEFAULT `'PENDING'` | `PENDING`, `APPROVED`, `REJECTED` |
| `created_at` | `DateTime(tz)` | NOT NULL | UTC timestamp |

---

## 4. REST API & WebSocket Wire Protocols

### 4.1 REST Endpoints
- `POST /api/v1/webhooks/orders` - Ingests new COD order, computes RTO risk score, creates `Order`, and queues an outbound call session.
- `GET /api/v1/orders` - Lists tenant orders with optional `status` filter.
- `POST /api/v1/calls/trigger-outbound/{order_id}` - Initializes an `OUTBOUND_VERIFY` session and returns `{session_id, ws_url}`.
- `POST /api/v1/calls/start-inbound` - Initializes an `INBOUND_RESCUE` session for buyer/rider and returns `{session_id, ws_url}`.
- `GET /api/v1/approvals` - Lists pending `ApprovalRequest` items.
- `POST /api/v1/approvals/{approval_id}/resolve` - Accepts `{approved: bool, operator_note: str}`, executes or aborts the paused tool, and notifies the active session.

### 4.2 WebSocket Protocol (`/ws/call/{session_id}`)
**Client-to-Server JSON Frames:**
```json
{"event": "audio_chunk", "pcm16_base64": "<base64-encoded-16kHz-mono-pcm>"}
{"event": "text_utterance", "text": "Yes, deliver near Masjid-e-Tooba after 4 PM"}
{"event": "barge_in"}
{"event": "hangup"}
```

**Server-to-Client JSON Frames:**
```json
{"event": "session_ready", "session_id": "...", "order": {...}, "direction": "OUTBOUND_VERIFY"}
{"event": "transcript_update", "role": "user|assistant", "text": "..."}
{"event": "tool_trace", "step": 1, "tool_name": "save_delivery_landmark", "arguments": {...}, "duration_ms": 14.2, "status": "SUCCESS|PAUSED_FOR_APPROVAL"}
{"event": "tts_audio", "wav_base64": "<base64-wav-chunk>", "sentence_index": 0}
{"event": "clear_audio"}
{"event": "telemetry", "stt_ms": 112.4, "llm_ms": 178.9, "tts_ms": 164.1, "total_ms": 455.4}
```