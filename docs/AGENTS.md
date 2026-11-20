# AGENTS.md - Coding Agent Operating Manual

## 1. Project Identity
**Project Name:** VanguardCOD (Autonomous COD Order Verification & Delivery Rescue SaaS)
**Architecture:** Multi-tenant FastAPI + Async PostgreSQL backend, framework-less `AsyncGroq` voice and calling agents, Dual-Mode WebSocket Telephony Bridge (Twilio PSTN + Browser WebRTC Softphone), and a React + TypeScript + Tailwind CSS operational console.

> **Compatibility Note:** If using Claude Code, symlink this file via `ln -s AGENTS.md CLAUDE.md`. If using Cursor, symlink or reference this file inside `.cursor/rules/`.

---

## 2. Non-Negotiable Engineering Rules
1. **Zero Orchestration Frameworks:** Do NOT install or import `langchain`, `langgraph`, `llama_index`, `crewai`, or `autogen`. All agent loops, tool registries, parallel tool execution (`asyncio.gather`), and state checkpoints must be written in native Python using `asyncio`, `pydantic` (v2), and the official `groq` Python SDK (`AsyncGroq`).
2. **Code Style & Cleanliness:**
   - Do not use emojis anywhere in source code, log statements, UI strings, or commit messages.
   - Do not write excessive or redundant inline comments. Code must be self-documenting through clear naming and strict Python/TypeScript type annotations.
   - Never use em dashes in UI copy, prompts, or documentation; use standard hyphens (`-`) or colons (`:`).
3. **Strict Async I/O:** Every database query (`SQLAlchemy` 2.0 + `asyncpg`), HTTP call (`httpx`), and LLM/Audio request (`AsyncGroq`) must be non-blocking. Wrap any unavoidable synchronous CPU/IO helper in `await asyncio.to_thread(...)`.
4. **Multi-Tenant Isolation:** Every database model and API query (except tenant creation) must filter by `tenant_id`. Never expose records across tenants.
5. **Anti-Template UI Aesthetic:** When building frontend components in `frontend/src/`, strictly follow `docs/DESIGN_SYSTEM.md`. Do not use generic AI template tropes (no purple/indigo gradients, no glowing neon blobs, no rounded-3xl marketing cards). Use the specified dark carbon/obsidian operational telemetry theme with crisp $1\text{ px}$ structural borders and monospace numerical metrics.

---

## 3. Repository Navigation & Progressive Disclosure
Before writing code for any module, read the relevant specification file:
- **Product Scope & User Flows:** `docs/PRD.md`
- **Schemas, API Contracts, & Groq Model Specs:** `docs/TRD.md`
- **Audio Pipeline, VAD Barge-In, & State Machine:** `docs/ARCHITECTURE.md`
- **UI Tokens, Layouts, & Component Specs:** `docs/DESIGN_SYSTEM.md`
- **Step-by-Step Build Queue:** `docs/TASKS.md`
- **Persistent Context & Architectural Decisions:** `MEMORY.md`

---

## 4. Standard Workspace Commands

### Backend (`backend/`)
- **Install dependencies:** `pip install -r requirements.txt`
- **Run development server:** `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- **Run test suite:** `pytest -v`
- **Type check:** `mypy app`

### Frontend (`frontend/`)
- **Install dependencies:** `npm install`
- **Run development server:** `npm run dev`
- **Build & Typecheck:** `npm run build`

---

## 5. Agent Workflow Protocol
When executing tasks from `docs/TASKS.md`:
1. Read `MEMORY.md` and `docs/TASKS.md` to identify the current active task.
2. Implement the required files with complete error handling and Pydantic/TypeScript validation.
3. Run the verification command listed for that task.
4. Update `docs/TASKS.md` (mark `[x]`) and append any new state or schema adjustments to `MEMORY.md`.