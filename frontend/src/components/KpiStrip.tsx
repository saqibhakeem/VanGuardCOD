import { Activity, BadgeCheck, ShieldCheck, Timer } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { CallSessionSummary, Order } from "../types";
import { formatMoney, formatMs, latencyTone, TONE_TEXT } from "../lib/format";

interface Props {
  orders: Order[];
  sessions: CallSessionSummary[];
}

interface Cell {
  label: string;
  value: string;
  hint: string;
  icon: LucideIcon;
  tone?: "verified" | "warning" | "critical" | "accent" | "neutral";
}

export function KpiStrip({ orders, sessions }: Props) {
  const verifiedOrders = orders.filter((order) => order.status === "VERIFIED");
  const verifiedVolume = verifiedOrders.reduce((total, order) => total + order.cod_amount, 0);

  const prevented = orders.filter(
    (order) =>
      (order.status === "VERIFIED" || order.status === "CANCELLED") &&
      order.rto_risk_score >= 50,
  );
  const riskPrevented = prevented.reduce((total, order) => total + order.cod_amount, 0);

  const measured = sessions
    .map((session) => session.avg_turn_latency_ms)
    .filter((value) => value > 0);
  const meanLatency = measured.length
    ? measured.reduce((total, value) => total + value, 0) / measured.length
    : 0;

  const activeSessions = sessions.filter(
    (session) => session.status === "ACTIVE" || session.status === "PAUSED_APPROVAL",
  ).length;

  const cells: Cell[] = [
    {
      label: "Verified COD Volume",
      value: formatMoney(verifiedVolume),
      hint: `${verifiedOrders.length} of ${orders.length} orders verified`,
      icon: BadgeCheck,
      tone: "verified",
    },
    {
      label: "RTO Risk Prevented",
      value: formatMoney(riskPrevented),
      hint: `${prevented.length} high risk orders resolved`,
      icon: ShieldCheck,
      tone: "accent",
    },
    {
      label: "Mean Turn Latency",
      value: measured.length ? formatMs(meanLatency) : "-",
      hint: measured.length
        ? `${measured.length} measured sessions, budget 650 ms`
        : "No measured turns yet",
      icon: Timer,
      tone: latencyTone(meanLatency),
    },
    {
      label: "Active Voice Sessions",
      value: String(activeSessions),
      hint: `${sessions.length} sessions in the last window`,
      icon: Activity,
      tone: activeSessions > 0 ? "accent" : "neutral",
    },
  ];

  return (
    <section
      className="grid grid-cols-2 gap-px border border-line bg-line lg:grid-cols-4"
      aria-label="Operational key metrics"
    >
      {cells.map((cell) => {
        const Icon = cell.icon;
        return (
          <div key={cell.label} className="bg-panel px-4 py-3.5">
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
                {cell.label}
              </span>
              <Icon className="h-3.5 w-3.5 text-ink-3" aria-hidden />
            </div>
            <div
              className={`mt-2 font-mono text-[20px] leading-6 tracking-[-0.01em] ${
                cell.tone ? TONE_TEXT[cell.tone] : "text-ink"
              }`}
            >
              {cell.value}
            </div>
            <div className="mt-1 truncate text-[11px] text-ink-3">{cell.hint}</div>
          </div>
        );
      })}
    </section>
  );
}
