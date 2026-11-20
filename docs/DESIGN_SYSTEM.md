# UI/UX & Design System Specification

## 1. Design Philosophy: "Obsidian Operational Telemetry"
The interface must look like a mission-critical telephony and logistics command center (taking structural cues from Linear, Raycast, and Vercel Observability), avoiding cliché AI-generated aesthetics.

### Strictly Banned Visual Patterns
- No purple, violet, or neon-pink gradients.
- No floating 3D glassmorphic blobs or decorative stock illustrations.
- No marketing landing-page hero sections inside the operational workspace.
- No emojis anywhere in navigation, status badges, or buttons.

---

## 2. Color Tokens (CSS Variables / Tailwind Config)

| Token Name | Hex Value | Usage |
| :--- | :--- | :--- |
| `--bg-canvas` | `#090A0F` | Primary application background |
| `--bg-surface-1` | `#11131A` | Primary panel, table, and card surface |
| `--bg-surface-2` | `#171A24` | Elevated drawer, hover row, and active softphone surface |
| `--border-subtle` | `#222634` | Hairline $1\text{ px}$ structural grid borders |
| `--border-focus` | `#3B82F6` | Active input, active call ring, and selected row border |
| `--text-primary` | `#F3F4F6` | Primary headings and active transcript text |
| `--text-secondary` | `#9CA3AF` | Table metadata, labels, and secondary descriptions |
| `--text-muted` | `#6B7280` | Timestamps, axis labels, and disabled states |
| `--signal-verified` | `#10B981` | Verified order badge, healthy latency ($\le 500\text{ ms}$), active audio |
| `--signal-warning` | `#F59E0B` | Pending human approval, elevated RTO risk ($50\text{--}75$) |
| `--signal-critical` | `#EF4444` | Cancelled order, high RTO risk ($>75$), barge-in interrupt flash |
| `--signal-accent` | `#06B6D4` | Outbound Calling Agent waveform & tool execution badge |

---

## 3. Typography Scale
- **UI & Prose Font (`--font-sans`):** `'Inter'`, `'Plus Jakarta Sans'`, or system sans-serif.
- **Telemetry, Transcripts, & IDs (`--font-mono`):** `'JetBrains Mono'` or `'Fira Code'` with `font-variant-numeric: tabular-nums` enforced on all latency numbers, currency amounts, phone numbers, and RTO risk scores.
- **Sizing:**
  - Page Header: `18px` (`font-semibold`, tracking `-0.01em`)
  - Section Header: `12px` uppercase (`font-mono`, tracking `0.08em`, color `--text-secondary`)
  - Table Cell / Body: `13px` (`leading-5`)
  - Micro Telemetry Badge: `11px` (`font-mono`)

---

## 4. Workspace Layout Architecture
Use a full-viewport (`h-screen overflow-hidden`) 3-zone grid divided by $1\text{ px}$ solid `#222634` borders:

1. **Left Navigation Rail (`w-56`):**
   - Tenant selector dropdown with live API status indicator dot ($6\text{ px}$ circle).
   - 4 primary views: `Operations Queue`, `Softphone Simulator Lab`, `HITL Approval Gate` (with numeric pending counter badge), and `Webhook & Voice Config`.
   - Bottom unit: Real-time Groq cost & latency ticker (`Whisper: $0.04/hr | Llama-3.3-70B | Orpheus TTS`).

2. **Center Primary Workspace (`flex-1 overflow-y-auto`):**
   - **Top KPI Strip:** 4 compact metric cells sharing a $1\text{ px}$ border grid: `Verified COD Volume`, `RTO Risk Prevented`, `Mean Turn Latency (ms)`, and `Active Voice Sessions`.
   - **Order Verification Table:** Dense operational table displaying `Order Ref`, `Customer & Phone`, `COD Amount`, `Address & Verified Landmark`, `RTO Risk Bar` (segmented horizontal meter), `Status Pill`, and quick-action button (`Trigger Outbound Call`).

3. **Right Live Telephony & Trace Inspector (`w-96` or `w-[440px]`):**
   - **Top Half (Interactive Softphone Simulator):**
     - Mode Switcher: `Outbound Call Receiver (Act as Buyer)` vs. `Inbound Rescue Dialer (Act as Rider/Buyer)`.
     - Dual-channel HTML5 Canvas audio visualizer showing Caller Input Waveform (`#10B981`) and Agent Output Waveform (`#06B6D4`).
     - Microphone push-to-talk / live WebRTC toggle + quick text injection input (for quiet environments without mic).
     - `Simulate Barge-In Interrupt` button.
   - **Bottom Half (Live Agent Execution Trace):**
     - Real-time chronological stream of `AgentStepTrace` items showing exact `stt_ms`, `llm_ms`, `tts_ms`, tool name, JSON arguments, and approval gate status.