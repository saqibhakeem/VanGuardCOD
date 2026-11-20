# VanguardCOD - Autonomous Voice AI for E-Commerce Cash-on-Delivery (COD)

VanguardCOD is a multi-tenant B2B SaaS platform engineered for e-commerce brands in cash-on-delivery markets (Pakistan, MENA, South Asia). It replaces manual call center order confirmation agents with autonomous, ultra-low latency voice AI that calls customers upon order placement, verifies addresses, checks delivery availability, flags Return-to-Origin (RTO) risks, and updates order states in real time.

---

## Architecture Overview

The system is structured as three decoupled components:

1. **Backend Engine (`backend/`)**:
   - High-throughput asynchronous FastAPI engine built natively with `asyncio`, Pydantic v2, and SQLAlchemy 2.0 (SQLite for local dev, PostgreSQL for production).
   - Autonomous Voice AI pipeline powered by Groq (`whisper-large-v3-turbo` for STT, `llama-3.3-70b-versatile` for reasoning, and `canopylabs/orpheus-v1-english` for TTS).
   - Bi-directional 16 kHz PCM audio WebSocket telephony bridge with RMS Voice Activity Detection (VAD) and sub-second barge-in support.
   - Deterministic Human-in-the-Loop (HITL) approval gate for high-risk order modifications and address rerouting.

2. **Merchant SaaS Portal (`frontend/`)**:
   - Modern, sleek B2B E-Commerce dashboard (Linear / Stripe inspired).
   - Store onboarding and self-serve business registration generating store API keys (`vcod_...`) and webhook URLs.
   - Live Order Queue with RTO risk meters, one-click manual call triggers, call session analytics, manager HITL approval inbox, and store integration settings.

3. **Customer Phone Simulator (`phone-simulator/`)**:
   - Completely separate standalone application simulating an end-customer smartphone.
   - Background listener that polls for incoming verification calls.
   - Synthesizes authentic dual-tone phone ringing via WebAudio API.
   - Live in-call interface with dual audio waveforms, microphone streaming, conversational bubbles, quick customer voice replies, and real-time AI latency breakdown.

---

## Quick Start Guide

### Prerequisites
- Python 3.11+
- Node.js 20+
- On Windows PowerShell, use `npm.cmd`

---

### Step 1: Start the Backend Server

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```
- API Base URL: `http://127.0.0.1:8100/api/v1`
- Swagger / OpenAPI Docs: `http://127.0.0.1:8100/docs`
- Health Check: `http://127.0.0.1:8100/health`

---

### Step 2: Run in Development Mode (Recommended for testing)

Open two separate terminals:

**Terminal A - Merchant SaaS Portal:**
```powershell
cd frontend
npm.cmd run dev
```
Accessible at: `http://localhost:5173/`

**Terminal B - Customer Phone Simulator:**
```powershell
cd phone-simulator
npm.cmd run dev
```
Accessible at: `http://localhost:5174/`

---

### Step 3: Run via Single Production Build (Zero Node.js runtime)

Both frontends can be built into static distribution bundles and served directly by the FastAPI backend:

```powershell
# Build both frontends
cd phone-simulator; npm.cmd run build
cd ../frontend; npm.cmd run build

# Start backend
cd ../backend; python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

- Merchant SaaS Console: `http://127.0.0.1:8100/console/`
- Customer Phone Simulator: `http://127.0.0.1:8100/phone/`

---

## How to Test the Verification Call Workflow

1. **Open the Customer Phone Simulator** in one browser window or screen:
   - Go to `http://localhost:5174/` (or `http://127.0.0.1:8100/phone/`).
   - The phone sits idle waiting for incoming calls.

2. **Open the Merchant SaaS Portal** in another window:
   - Go to `http://localhost:5173/` (or `http://127.0.0.1:8100/console/`).
   - Sign in using a demo account (e.g., Click **Store Owner & Administrator**) or register a new store.

3. **Trigger an Outbound Verification Call**:
   - In the **Orders Queue**, find an unverified order (status `PENDING_CALL`).
   - Click the **"Call Customer"** button.

4. **Watch the Customer Phone Ring**:
   - The Customer Phone Simulator will immediately ring with animated phone ringer chime.
   - Click the green **Answer** button.

5. **Interact with the AI Voice Agent**:
   - The AI agent greets the customer and confirms the order details.
   - You can speak directly into your microphone, or click quick reply buttons (e.g., *"Yes, please confirm and deliver tomorrow evening"*).
   - Interrupt the agent at any time by speaking or clicking **Barge In**.
   - Watch the live dual waveform and real-time sub-second latency breakdown.

6. **Order Verification & Status Update**:
   - Once the customer confirms, the AI calls the `confirm_cod_order` tool.
   - Switch back to the Merchant SaaS Portal: the order status updates to **VERIFIED** automatically.

---

## Store Onboarding & API Integration

### Registering a New Store
1. On the login screen, click **"Register Brand"**.
2. Enter your Store Name, Administrator Username, and Password.
3. Configure your Default Language (English / Urdu) and AI Voice Persona (Hannah / Troy / Alex / Evelyn).
4. The system automatically creates your isolated tenant workspace and issues your store API key:
   ```
   vcod_...
   ```

### Webhook Ingestion (Shopify, WooCommerce, Custom Forms)
Whenever a COD order is placed in your store, send a POST request to:
```http
POST /api/v1/webhooks/orders
Header: X-Tenant-API-Key: vcod_your_store_key
Content-Type: application/json

{
  "external_order_id": "ORD-10492",
  "customer_name": "Ayesha Khan",
  "customer_phone": "+923001234567",
  "items_summary": "Silk Embroidered Kurti (Medium)",
  "cod_amount": 3950.00,
  "raw_address": "House 12, Street 4, Sector F-8/2, Islamabad",
  "payment_method": "COD"
}
```
The system calculates the RTO risk score, schedules an outbound verification call, and rings the customer.

---

## Running the Automated Test Suite

From the `backend/` directory:
```powershell
python -m pytest -q
```
Suite status: **61 passed in 9.07s**.
Tests cover database operations, multi-tenant isolation, RTO risk scoring, autonomous agent runtime, Orpheus TTS chunking, RMS VAD barge-in, WebSocket telephony sessions, and SaaS authentication.
