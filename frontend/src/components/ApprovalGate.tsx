import { ArrowUpRight, RefreshCw, ShieldCheck } from "lucide-react";

import type { Approval, ApprovalStatus } from "../types";
import { formatDateTime, formatMoney, humanize, shortId } from "../lib/format";
import { StatusPill } from "./StatusPill";
import { Button, SectionLabel } from "./ui";

type Filter = ApprovalStatus | "ALL";

interface Props {
  approvals: Approval[];
  filter: Filter;
  loading: boolean;
  onFilter: (filter: Filter) => void;
  onOpen: (approvalId: string) => void;
  onRefresh: () => void;
}

const FILTERS: Filter[] = ["PENDING", "APPROVED", "REJECTED", "ALL"];

function previewValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (key === "cod_amount" && typeof value === "number") return formatMoney(value);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function ApprovalGate({
  approvals,
  filter,
  loading,
  onFilter,
  onOpen,
  onRefresh,
}: Props) {
  const filtered = approvals.filter(
    (approval) => filter === "ALL" || approval.status === filter,
  );
  const pending = approvals.filter((approval) => approval.status === "PENDING").length;

  return (
    <section className="border border-line bg-panel">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2.5">
        <SectionLabel>Human in the loop</SectionLabel>
        <div className="ml-2 flex border border-line">
          {FILTERS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => onFilter(option)}
              aria-pressed={filter === option}
              className={`border-r border-line px-2 py-1 font-mono text-[9px] uppercase tracking-[0.08em] last:border-r-0 ${
                filter === option
                  ? "bg-panel-2 text-ink"
                  : "text-ink-3 hover:text-ink-2"
              }`}
            >
              {option}
            </button>
          ))}
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-3">
          {pending} pending
        </span>
        <Button size="sm" onClick={onRefresh} disabled={loading} className="ml-auto">
          <RefreshCw
            className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`}
            aria-hidden
          />
          Refresh
        </Button>
      </div>

      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 px-4 py-16 text-center">
          <ShieldCheck className="h-7 w-7 text-ink-3" aria-hidden />
          <div className="text-[13px] text-ink-2">No approvals in this state</div>
          <div className="max-w-sm text-[11px] leading-5 text-ink-3">
            Trigger a call and ask for a price change or address reroute. High value mutations
            pause here for an operator decision.
          </div>
        </div>
      ) : (
        <div className="grid gap-px bg-line lg:grid-cols-2">
          {filtered.map((approval) => {
            const entries = Object.entries(approval.proposed_arguments).slice(0, 4);
            return (
              <article key={approval.id} className="flex flex-col gap-2 bg-panel px-4 py-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[12px] text-ink">
                    {approval.order_reference ?? shortId(approval.order_id)}
                  </span>
                  <StatusPill status={approval.status} />
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-accent">
                    {humanize(approval.tool_name)}
                  </span>
                  <span className="font-mono text-[9px] text-ink-3">
                    {formatDateTime(approval.created_at)}
                  </span>
                </div>
                <p className="line-clamp-2 text-[11px] leading-4 text-ink-2">{approval.reason}</p>
                <div className="flex flex-wrap gap-1">
                  {entries.map(([key, value]) => (
                    <span
                      key={key}
                      className="border border-line bg-panel-2 px-1.5 py-0.5 font-mono text-[9px] text-ink-3"
                    >
                      {key}: {previewValue(key, value)}
                    </span>
                  ))}
                </div>
                <div className="mt-1 flex justify-end">
                  <Button size="sm" onClick={() => onOpen(approval.id)}>
                    {approval.status === "PENDING" ? "Review" : "Inspect"}
                    <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
                  </Button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
