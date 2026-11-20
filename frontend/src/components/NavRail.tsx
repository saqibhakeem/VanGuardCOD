import {
  KeyRound,
  LayoutGrid,
  PhoneCall,
  ShieldCheck,
  Webhook,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { ViewKey } from "../types";

interface NavItem {
  key: ViewKey;
  label: string;
  icon: LucideIcon;
  badge?: number;
}

interface Props {
  view: ViewKey;
  onChange: (view: ViewKey) => void;
  apiKey: string;
  onApiKeyChange: (value: string) => void;
  approvalCount: number;
  health: "up" | "down" | "checking";
  tenantName: string;
  mockMode: boolean;
}

const HEALTH_LABEL = {
  up: "Backend online",
  down: "Backend unreachable",
  checking: "Checking backend",
};

const HEALTH_DOT = {
  up: "bg-verified",
  down: "bg-critical",
  checking: "bg-warning",
};

export function NavRail({
  view,
  onChange,
  apiKey,
  onApiKeyChange,
  approvalCount,
  health,
  tenantName,
  mockMode,
}: Props) {
  const items: NavItem[] = [
    { key: "operations", label: "Operations Queue", icon: LayoutGrid },
    { key: "sessions", label: "Call Sessions & Telemetry", icon: PhoneCall },
    {
      key: "approvals",
      label: "HITL Approval Gate",
      icon: ShieldCheck,
      badge: approvalCount,
    },
    { key: "integrations", label: "Store & Sheets Sync", icon: Webhook },
    { key: "config", label: "Webhook and Voice Config", icon: Webhook },
  ];


  return (
    <aside className="hidden w-56 shrink-0 flex-col border-r border-line bg-panel md:flex">
      <div className="flex items-center gap-2.5 border-b border-line px-4 py-4">
        <div className="grid h-9 w-9 place-items-center border border-line bg-panel-2 font-mono text-[11px] tracking-[0.08em] text-accent">
          VC
        </div>
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold tracking-[-0.01em]">
            VanguardCOD
          </div>
          <div className="truncate font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
            COD Rescue Ops
          </div>
        </div>
      </div>

      <div className="border-b border-line px-4 py-3">
        <div className="flex items-center justify-between">
          <span className="font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
            Tenant
          </span>
          <span className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-2">
            <span
              className={`h-1.5 w-1.5 rounded-full ${HEALTH_DOT[health]} ${
                health === "up" ? "animate-pulse" : ""
              }`}
            />
            {HEALTH_LABEL[health]}
          </span>
        </div>
        <div className="mt-1 truncate text-[12px] text-ink">{tenantName}</div>
        <label className="mt-3 flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
          <KeyRound className="h-3 w-3" aria-hidden />
          Tenant API key
        </label>
        <input
          type="password"
          value={apiKey}
          onChange={(event) => onApiKeyChange(event.target.value)}
          spellCheck={false}
          autoComplete="off"
          aria-label="Tenant API key"
          className="mt-1 w-full border border-line bg-panel-2 px-2 py-1.5 font-mono text-[11px] text-ink outline-none focus:border-focus"
        />
        <div className="mt-2 flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              mockMode ? "bg-warning" : "bg-verified"
            }`}
          />
          {mockMode ? "Mock voice runtime" : "Groq live runtime"}
        </div>
      </div>

      <nav className="flex flex-col gap-1 p-2">
        {items.map((item) => {
          const Icon = item.icon;
          const active = view === item.key;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => onChange(item.key)}
              aria-current={active ? "page" : undefined}
              className={`flex items-center gap-2.5 border px-2.5 py-2 text-left text-[12px] transition-colors ${
                active
                  ? "border-line bg-panel-2 text-ink"
                  : "border-transparent text-ink-2 hover:border-line hover:bg-panel-2/60 hover:text-ink"
              }`}
            >
              <Icon
                className={`h-4 w-4 shrink-0 ${active ? "text-accent" : "text-ink-3"}`}
                aria-hidden
              />
              <span className="min-w-0 flex-1 leading-4">{item.label}</span>
              {item.badge && item.badge > 0 ? (
                <span className="border border-warning/40 bg-warning/10 px-1.5 py-0.5 font-mono text-[10px] text-warning">
                  {item.badge}
                </span>
              ) : null}
            </button>
          );
        })}
      </nav>

      <div className="mt-auto border-t border-line px-4 py-3">
        <div className="font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
          Runtime pricing
        </div>
        <div className="mt-2 space-y-1.5 font-mono text-[10px] text-ink-2">
          <div className="flex justify-between gap-2">
            <span>Whisper turbo</span>
            <span className="text-ink-3">$0.04/hr</span>
          </div>
          <div className="flex justify-between gap-2">
            <span>Llama 3.3 70B</span>
            <span className="text-ink-3">$0.59/M in</span>
          </div>
          <div className="flex justify-between gap-2">
            <span>Orpheus TTS</span>
            <span className="text-ink-3">200 char cap</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
