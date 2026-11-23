# VanguardCOD - Autonomous Voice & WhatsApp AI for E-Commerce Cash-on-Delivery (COD)

VanguardCOD is a multi-tenant B2B SaaS platform engineered for e-commerce brands in cash-on-delivery markets (Pakistan, MENA, South Asia). It replaces manual call center order confirmation agents with autonomous, ultra-low latency voice and WhatsApp conversational AI that verifies customer orders, negotiates delivery landmarks, handles address reroutes, flags Return-to-Origin (RTO) risks, and updates order states in real time.

---

## Architecture Overview

VanguardCOD is structured as two high-performance decoupled components with Bring-Your-Own-Key (BYOK) provider integrations:

1. **Backend Engine (`backend/`)**:
   - High-throughput asynchronous FastAPI engine built with `asyncio`, Pydantic v2, and SQLAlchemy 2.0 (SQLite for local dev, PostgreSQL for production).
   - Autonomous Voice AI pipeline powered by Groq (`whisper-large-v3-turbo` for STT, `llama-3.3-70b-versatile` for reasoning, and `canopylabs/orpheus-v1-english` for TTS).
   - Real **Twilio Voice Telephony** bridge supporting dynamic TwiML and bi-directional WebSocket Media Streams with 8 kHz $\mu$-law $\leftrightarrow$ 16 kHz PCM16 transcoding.
   - Real **WhatsApp Conversational Chat Agent** driven by Meta WhatsApp Cloud API (v19.0) and Twilio WhatsApp for multi-turn natural language verification.
   - Smart **Omnichannel Verification Dispatcher** (`WHATSAPP_FIRST` or `VOICE_FIRST` with automated fallback).
   - Deterministic Human-in-the-Loop (HITL) approval gate for high-risk order modifications and address rerouting.

2. **Merchant SaaS Portal (`frontend/`)**:
   - Modern, sleek B2B E-Commerce dashboard (Linear / Stripe inspired).
   - Self-serve business onboarding with live communication channel selection (`WHATSAPP`, `TWILIO`, or `BOTH`).
   - BYOK provider credentials management with real-time connection verification.
   - Live Order Queue with RTO risk meters, channel status badges, one-click manual verification dispatchers, call session analytics, manager HITL approval drawer, and store integration settings.

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
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100 --reload
```
- API Base URL: `http://127.0.0.1:8100/api/v1`
- Swagger / OpenAPI Docs: `http://127.0.0.1:8100/docs`
- Health Check: `http://127.0.0.1:8100/health`

---

### Step 2: Start the Merchant SaaS Portal

In a second terminal:
```powershell
cd frontend
npm.cmd run dev
```
Accessible at: `http://localhost:5173/`

---

### Step 3: Run via Single Production Build (Optional)

The frontend can be compiled into a static distribution bundle and served directly by the FastAPI backend at `/console/`:

```powershell
# Build frontend
cd frontend; npm.cmd run build

# Start backend
cd ../backend; python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```
- Merchant SaaS Console: `http://127.0.0.1:8100/console/`

---

## How to Test the SaaS Verification Workflow

### 1. Register a Store & Choose Communication Channels
1. Open `http://localhost:5173/` and click **Register New Store / Brand**.
2. Enter your business name, administrator username, and password.
3. Under **Choose Verification Channel(s)**, select:
   - **WhatsApp Chat Agent**: Multi-turn conversational chat on WhatsApp.
   - **Twilio Phone Call**: Autonomous outbound voice AI calls.
   - **Both (Omnichannel)**: Smart hybrid routing with automatic fallback.
4. Input your provider credentials (or use mock mode) and click **Test Connection** for live validation.
5. Complete registration to receive your store API key (`vcod_...`) and webhook ingestion URL.

### 2. Verify Incoming Orders
1. In the **Operations** tab, view incoming COD orders.
2. Click **Verify Call** to trigger an autonomous Twilio voice call.
3. Click **WhatsApp** to initiate a multi-turn WhatsApp chat session.
4. The customer receives the verification message or phone call, confirms their order, and provides their landmark.
5. The order status updates automatically to **VERIFIED** with the verified landmark saved in real time.

---

## Store Onboarding & API Integration

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
The system calculates the RTO risk score, schedules autonomous verification via the store's configured channels, and protects your inventory against return-to-origin loss.

---

## Running the Automated Test Suite

From the repository root:
```powershell
pytest backend/tests/
```
Suite status: **70 passed in 15.91s (100% pass rate)**.
Tests cover database operations, multi-tenant isolation, RTO risk scoring, autonomous voice agent runtime, Twilio voice media streams, WhatsApp conversational agent, omnichannel dispatch, and SaaS authentication.
