# Product Requirements Document (PRD): VanguardCOD SaaS

## 1. Problem Statement & Commercial Context
E-commerce merchants operating in Cash-on-Delivery (COD) markets lose $15\%$ to $30\%$ of gross revenue to Return-to-Origin (RTO) shipments caused by:
1. Unverified or impulse checkouts with fake phone numbers.
2. Incomplete street addresses lacking local landmarks.
3. Failed first-attempt courier deliveries where the rider marks the buyer as unreachable without merchant visibility.

Manual call-center verification takes $2$ to $12\text{ hours}$ per order and costs $\$3.00$ to $\$8.00$ per resolved incident. VanguardCOD automates both halves of the lifecycle in real time at roughly $\$0.03$ to $\$0.08$ per call using Groq LPU inference.

---

## 2. Core User Personas
1. **Merchant Operations Manager (Tenant Admin):** Connects Shopify/WooCommerce webhooks, configures RTO risk rules, monitors live voice calls, and approves/rejects paused high-risk agent actions.
2. **End Buyer (Customer):** Receives an automated Outbound Verification Call within $15\text{ seconds}$ of checkout to confirm intent and provide a delivery landmark, or calls the Inbound Rescue Line to reschedule a delivery.
3. **Field Courier / Delivery Rider:** Calls the Inbound Rescue Voice Agent when standing outside a locked gate or unnumbered street to get instant landmark instructions or trigger an automated bridge/coordinate update with the buyer.

---

## 3. Core Product Capabilities

### 3.1 Automated Outbound Calling Agent (Checkout Verifier)
- **Trigger:** Fired automatically when an order webhook arrives at `/api/v1/webhooks/orders` with payment method `COD`.
- **Pre-Call Heuristic Scoring:** Calculates an initial RTO Risk Score ($0$ to $100$) based on address completeness, house number presence, and COD order value.
- **Conversation Objectives:**
  1. Greet the customer by name and state the merchant name, item summary, and exact COD payable amount.
  2. Confirm whether the customer wants the order dispatched (`VERIFIED`) or cancelled (`CANCELLED`).
  3. If the raw address lacks a landmark or house number, ask for a nearby landmark and delivery time window.
  4. Execute `update_order_verification` tool deterministically.

### 3.2 Interactive Inbound Voice Agent (Delivery Rescue Desk)
- **Trigger:** Inbound call from a buyer or delivery rider (via PSTN or the built-in Browser WebRTC Softphone Simulator).
- **Conversation Objectives:**
  1. Identify the caller via phone number or spoken Order ID (`lookup_order_context`).
  2. **Rider Flow:** Provide verified landmark notes, log a failed delivery attempt with reason (`log_rider_issue`), or update the pin/window.
  3. **Buyer Flow:** Answer order status inquiries, reschedule delivery windows (`reschedule_delivery`), or request an address change.

### 3.3 Human-in-the-Loop (HITL) Escalation Gate
- Any tool call that mutates high-risk fields (such as changing the delivery address to a different sector/city, discounting the COD amount, or approving an order exceeding the tenant's `max_auto_approve_cod` threshold) must pause agent execution and create an `ApprovalRequest`.
- The Merchant Dashboard displays a live diff of current vs. proposed values for one-click approval or rejection.

### 3.4 Built-In Browser Softphone Lab (Zero-Cost Demo Mode)
- Allows merchants, developers, and portfolio evaluators to test both **Outbound Verification Calls** (browser rings as the customer's phone) and **Inbound Rescue Calls** (user dials in as buyer or rider) directly in the browser over WebSockets without needing a paid Twilio phone number.

---

## 4. Target Performance & Success Metrics
- **End-to-End Voice Turn Latency:** $\le 650\text{ ms}$ p95 (combined STT + LLM tool reasoning + first TTS audio chunk).
- **Barge-In Interruption Latency:** $\le 150\text{ ms}$ to clear outbound audio upon detecting caller speech.
- **Tool Schema Validity:** $100\%$ strict Pydantic validation before database commit.