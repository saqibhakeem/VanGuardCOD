# VanguardCOD

### Autonomous Voice & WhatsApp AI for E-Commerce Cash-on-Delivery (COD)

![Python 3.12](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![React 19](https://img.shields.io/badge/React-19.0-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white)
![Vite 7](https://img.shields.io/badge/Vite-7.3-646CFF?logo=vite&logoColor=white)
![Tailwind CSS v4](https://img.shields.io/badge/Tailwind_CSS-v4.0-06B6D4?logo=tailwindcss&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-LLaMA_3.3_70B_%7C_Whisper-F55036)
![Meta WhatsApp](https://img.shields.io/badge/WhatsApp-Cloud_API_v19.0-25D366?logo=whatsapp&logoColor=white)
![Twilio](https://img.shields.io/badge/Twilio-Voice_Media_Streams-F22F46?logo=twilio&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-71%20Passed-10B981?logo=pytest&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue)

VanguardCOD is a multi-tenant B2B SaaS platform engineered for e-commerce brands in cash-on-delivery (COD) markets (Pakistan, MENA, South Asia). It replaces high-cost, error-prone manual call centers with autonomous, ultra-low latency Voice and WhatsApp conversational AI that verifies customer purchase intent, confirms delivery landmarks, manages address alterations, calculates Return-to-Origin (RTO) risk scores, and routes high-risk modifications to a Human-in-the-Loop (HITL) approval dashboard in real time.

---

## The Problem & Market Context

In emerging e-commerce markets:
- **60% to 75%** of all transactions are paid via Cash on Delivery (COD).
- **20% to 35%** of unverified COD orders end in **Return-to-Origin (RTO)** due to fake orders, impulse buyers, incorrect addresses, or missing landmarks.
- Merchants lose billions in non-refundable two-way courier delivery fees, locked inventory, and manual verification call center overhead.

**VanguardCOD solves this** by executing automated, sub-second natural language verification over phone calls and WhatsApp immediately upon checkout.

---

## Core Capabilities

- **Ultra-Low Latency Autonomous Voice Agent ($\le 650\text{ ms}$)**:
  - Framework-less `AsyncGroq` agent runtime without heavy abstraction overhead (no LangChain / LangGraph).
  - Speech-to-Text: `whisper-large-v3-turbo` with real-time audio chunking.
  - Reasoning: `llama-3.3-70b-versatile` running multi-turn verification and tool dispatch.
  - Text-to-Speech: `canopylabs/orpheus-v1-english` streaming $200$-character clause chunks.
  - Hardware-level RMS Energy Barge-In Detector ($500.0\text{ RMS}$ threshold, $<50\text{ ms}$ interrupt reaction).
- **Meta WhatsApp Cloud API Agent**:
  - Full bidirectional webhook support for Meta Cloud API (v19.0) and Twilio WhatsApp.
  - Multi-turn natural language verification, address confirmation, and landmark capture.
  - Automatic phone normalization to E.164 without leading `+` for Meta standards.
- **Real-Time Human-In-The-Loop (HITL) Resolution Engine**:
  - Automatically gates sensitive operations (e.g. price discounts, city reroutes, high-value confirmations).
  - **Instant WhatsApp Customer Notification**: When an admin approves or rejects a request in the dashboard, the customer immediately receives an outbound WhatsApp message with the decision and admin note.
  - **Anti-Loop Deduplication & Approval Memory**: Injects past decisions into the agent prompt, prevents duplicate approval tickets, and returns polite hold replies while requests are pending.
- **Dynamic RTO Risk Engine (0-100 Score)**:
  - Heuristic risk breakdown evaluating address completeness, suspicious phone prefixes, order value thresholds, and city logistics profiles.
- **Telephony Lifecycle & Automated Retry Scheduling**:
  - 25-second ring timeout, missed call handling, and automated 2-hour retry scheduling on `no-answer` or `busy`.
  - Fast-forward "Retry Now" button for instant testing.
- **Zero-Setup Testing Suite**:
  - Built-in browser softphone simulator served at `/softphone` with WebAudio microphone capture, waveform visualizer, and live telemetry.
  - Deterministic zero-key mock runtime allowing full test execution without paid API keys.

---

## Architecture Overview

```text
+---------------------------------------------------------------------------------------+
|                          MERCHANT OPERATIONS & TESTING SUITE                          |
|  [Order Queue & SaaS Table]   [Customer Phone Simulator]   [HITL Authorization Inbox] |
+--------+---------------------------------+----------------------------+---------------+
         | REST                            | WS Audio/JSON              | REST
         v                                 v                            v
+---------------------------------------------------------------------------------------+
|                               FASTAPI ASYNC GATEWAY                                   |
|  +-----------------------------+  +------------------------+  +--------------------+  |
|  | Webhook & Ingestion API     |  | Dual-Mode Telephony    |  | Meta WhatsApp API  |  |
|  | - RTO Risk Engine (0-100)   |  | - WebRTC Browser PCM16 |  | - Webhook Verify   |  |
|  | - Channel Policy Router     |  | - Twilio PSTN Gateway  |  | - Inbound Messages |  |
|  +--------------+--------------+  +-----------+------------+  +---------+----------+  |
|                 |                             |                         |             |
|                 v                             v                         v             |
|  +-----------------------------+  +------------------------+  +--------------------+  |
|  | Framework-less AsyncGroq    |  | Voice Pipeline & VAD   |  | WhatsApp Chat      |  |
|  | - OutboundVerifierAgent     |  | - RMS Barge-In (500)   |  | Agent Runner       |  |
|  | - InboundRescueAgent        |  | - Groq STT (Whisper)   |  | - LLaMA 3.3 70B    |  |
|  | - Parallel Tool Dispatch    |  | - Orpheus TTS Streamer |  | - Approval Prompts |  |
|  +--------------+--------------+  +-----------+------------+  +---------+----------+  |
|                 |                             |                         |             |
|                 +-----------------------------+-------------------------+             |
|                                               |                                       |
|                                               v                                       |
|  +---------------------------------------------------------------------------------+  |
|  |                       DETERMINISTIC HITL CHECKPOINT GATE                        |  |
|  |  - Order Modification Checkpointing                                             |  |
|  |  - Anti-Loop Approval Deduplication                                             |  |
|  |  - Real-Time WhatsApp Customer Resolution Dispatch                              |  |
|  +--------------------------------------------+------------------------------------+  |
+-----------------------------------------------|---------------------------------------+
                                                |
                                                v
+---------------------------------------------------------------------------------------+
|                       POSTGRESQL / SQLITE ASYNC LEDGER                                |
|        [tenants]       [orders]       [call_sessions]       [approval_requests]       |
+---------------------------------------------------------------------------------------+
```

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Backend API** | Python 3.12, FastAPI, AsyncIO, Pydantic v2, SQLAlchemy 2.0 (Async), aiosqlite / asyncpg |
| **AI Inference** | Groq (`llama-3.3-70b-versatile`, `whisper-large-v3-turbo`, `canopylabs/orpheus-v1-english`) |
| **Channels** | Meta WhatsApp Cloud API (v19.0), Twilio Voice (TwiML & Media Streams), WebAudio WebRTC |
| **Frontend Portal** | React 19, TypeScript 5.9, Vite 7, Tailwind CSS v4 (`@tailwindcss/vite`), Lucide Icons |
| **Testing** | Pytest, Pytest-Asyncio, AnyIO (71 automated tests, 100% pass rate) |

---

## Quick Start Guide

### Prerequisites
- **Python**: 3.11 or 3.12
- **Node.js**: 20+
- **Groq API Key**: (Optional for production inference; mock mode runs deterministically without keys)

---

### Step 1: Backend Setup & Launch

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .venv\Scripts\Activate.ps1
   # macOS/Linux:
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure environment variables:
   ```bash
   cp .env.example .env
   ```
   *(Add your `GROQ_API_KEY`. If left empty, the system automatically runs the deterministic mock planner).*
5. Start the server:
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8100 --reload
   ```
   - API Base URL: `http://127.0.0.1:8100/api/v1`
   - Swagger OpenAPI Docs: `http://127.0.0.1:8100/docs`
   - Health Check: `http://127.0.0.1:8100/health`
   - Built-in Softphone Simulator: `http://127.0.0.1:8100/softphone`

---

### Step 2: Frontend Setup & Launch

In a separate terminal:
```bash
cd frontend
npm install
npm run dev
```
*(On Windows PowerShell, use `npm.cmd` if script execution is restricted).*

Open your browser to: **`http://localhost:5173/`**

---

### Step 3: (Optional) Live Meta WhatsApp Integration with Ngrok

Because Meta WhatsApp Cloud API requires a public HTTPS webhook endpoint:

1. Expose your local backend port:
   ```bash
   ngrok http 8100
   ```
2. Copy the generated HTTPS forwarding URL (e.g. `https://your-domain.ngrok-free.app`).
3. In your **Meta App Dashboard** (WhatsApp > Configuration):
   - **Callback URL**: `https://your-domain.ngrok-free.app/api/v1/whatsapp/webhook`
   - **Verify Token**: Set your chosen verify token (matching `WHATSAPP_VERIFY_TOKEN` in `backend/.env`).
   - Subscribe to the `messages` webhook field.
4. In `frontend/.env`, set:
   ```env
   VITE_BACKEND_URL=https://your-domain.ngrok-free.app
   ```
   The Vite proxy in `frontend/vite.config.ts` automatically handles `ngrok-skip-browser-warning` headers.

---

## Testing the SaaS Verification Workflow

### 1. Self-Serve Store Onboarding
1. Open `http://localhost:5173/` and click **Register New Store / Brand**.
2. Enter your store name (e.g. *Karachi Threads*), administrator username, and password.
3. Select your preferred channel mode:
   - **WhatsApp Chat Agent**: Multi-turn text verification on WhatsApp.
   - **Twilio Voice Call**: Autonomous outbound voice AI calls.
   - **Both (Omnichannel)**: Voice verification with automated WhatsApp fallback.
4. Complete registration to receive your tenant API key (`vcod_...`) and webhook ingestion URL.

### 2. Ingesting Orders via Webhook
Post a sample COD order from Shopify, WooCommerce, or your store backend:
```http
POST /api/v1/webhooks/orders
Header: X-Tenant-API-Key: vcod_your_store_key
Content-Type: application/json

{
  "external_order_id": "ORD-9042",
  "customer_name": "Hamza Abbasi",
  "customer_phone": "+923001234567",
  "items_summary": "Lawn Embroidered 3-Piece Suit (Teal)",
  "cod_amount": 8950.00,
  "raw_address": "House 42, Street 8, Sector F-7/1, Islamabad",
  "payment_method": "COD"
}
```
The engine evaluates the RTO risk score and schedules automated verification.

### 3. Human-In-The-Loop Approval & Real-Time WhatsApp Dispatch
1. If a customer on WhatsApp requests a price discount or address reroute:
   - The agent pauses the session and replies: *"Let me confirm that with our operations team. Please hold for a moment."*
   - An approval ticket appears immediately in the manager's **Approvals** drawer.
2. If the admin clicks **Reject** with a note (e.g. *"Discounts not available on this collection"*):
   - The customer instantly receives an outbound WhatsApp notification explaining the decision and asking whether to proceed with the original order or cancel.
   - If the customer messages again, the agent enforces the decision without spawning duplicate tickets.

---

## Running the Automated Test Suite

Run the full backend test suite:
```bash
pytest backend/tests/ -v
```

**Test Suite Coverage:**
```text
============================== 71 passed in 16.79s ==============================
- test_orders.py: Order ingestion, E.164 normalization, RTO risk scoring (10 tests)
- test_agent_runtime.py: Framework-less agent loop, parallel tools, HITL checkpoints (12 tests)
- test_voice_pipeline.py: STT Whisper, Orpheus TTS clause chunking, RMS VAD barge-in (13 tests)
- test_ws_call.py: Dual-mode WebSocket telephony, audio streaming, reconnect grace (11 tests)
- test_voice_session.py: Single-writer audio controller and interrupt epochs (4 tests)
- test_softphone_page.py: Embedded softphone simulator endpoint verification (2 tests)
- test_console_api.py: SaaS authentication, multi-tenant isolation, retry scheduler (11 tests)
- test_channels_and_omnichannel.py: Meta WhatsApp Cloud API, Twilio Voice TwiML,
  status callbacks, and real-time approval resolution dispatch with deduplication (8 tests)
```

---

## Project Structure

```text
VanGuardCOD/
├── backend/
│   ├── app/
│   │   ├── agents/          # Native AsyncGroq agents, tools, and HITL gate
│   │   │   ├── hitl.py      # Approval gate with deduplication
│   │   │   ├── runtime.py   # AutonomousVoiceAgent & ToolRegistry
│   │   │   └── tools.py     # Gated & ungated tool definitions
│   │   ├── api/             # REST & WebSocket route handlers
│   │   │   ├── approvals.py # HITL resolution & notification trigger
│   │   │   ├── channels.py  # Provider credential validators
│   │   │   ├── telephony.py # Twilio Voice TwiML & status callbacks
│   │   │   └── webhooks.py  # Order ingestion & Meta WhatsApp webhook
│   │   ├── db/              # SQLAlchemy models, sessions, and schemas
│   │   ├── services/        # Business logic & channel runners
│   │   │   ├── rto_scorer.py       # Heuristic RTO risk engine
│   │   │   └── whatsapp_agent.py   # LLaMA 3.3 WhatsApp conversational runner
│   │   └── voice/           # STT, TTS, VAD barge-in, & audio controllers
│   └── tests/               # 71 async pytest test cases
├── frontend/
│   ├── src/
│   │   ├── components/      # SaaS data tables, KPI cards, approval drawers
│   │   ├── views/           # Orders, sessions, config, store onboarding
│   │   └── api.ts           # Type-safe client for backend REST & WS APIs
│   ├── vite.config.ts       # Vite proxy config with ngrok header bypass
│   └── package.json
└── docs/                    # Architecture, ADRs, PRD, TRD, and Task Tracker
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
