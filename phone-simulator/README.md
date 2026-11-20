# VanguardCOD - Standalone Customer Phone Simulator

An independent handset simulator application simulating a customer in Pakistan receiving autonomous Cash on Delivery (COD) order verification calls from your e-commerce store.

## Architecture
- Completely isolated and decoupled from the VanguardCOD SaaS Merchant Portal.
- Connects to the VanguardCOD backend via:
  - Polling `GET /api/v1/calls/pending-outbound` (auto-detects when an order verification call is initiated).
  - WebSocket `/ws/call/{session_id}` (streams audio, VAD barge-in, transcript, and real-time telemetry).
- Synthesizes authentic dual-tone phone ringing (440Hz + 480Hz) via browser WebAudio API.
- Live dual audio streams, mic capture with PCM16 downsampling, interactive quick customer replies, and delivery rescue dialer.

## How to Run

1. Install dependencies:
```bash
npm install
```

2. Start the simulator dev server:
```bash
npm run dev
```
Runs at: `http://localhost:5174/`

When any order is placed in your store or verified from the VanguardCOD SaaS Portal, this phone handset will immediately ring!
