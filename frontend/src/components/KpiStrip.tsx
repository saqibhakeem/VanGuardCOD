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
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
      aria-label="Operational key metrics"
    >
      {cells.map((cell) => {
        const Icon = cell.icon;
        return (
          <div
            key={cell.label}
            className="bg-white border border-slate-200 rounded-md p-4 shadow-xs transition-shadow hover:shadow-sm"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                {cell.label}
              </span>
              <div className="p-1.5 rounded-sm bg-slate-50 text-slate-600">
                <Icon className="h-4 w-4" aria-hidden />
              </div>
            </div>
            <div
              className={`mt-2 text-2xl font-bold tracking-tight ${
                cell.tone ? TONE_TEXT[cell.tone] : "text-slate-900"
              }`}
            >
              {cell.value}
            </div>
            <div className="mt-1 truncate text-xs text-slate-500">{cell.hint}</div>
          </div>
        );
      })}
    </section>
  );

}
