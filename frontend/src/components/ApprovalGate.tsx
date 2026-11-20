import { ArrowUpRight, RefreshCw, ShieldCheck } from "lucide-react";

import type { Approval, ApprovalStatus } from "../types";
import { formatDateTime, formatMoney, humanize, shortId } from "../lib/format";
import { StatusPill } from "./StatusPill";
import { Button } from "./ui";


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
    <section className="border border-slate-200 bg-white rounded-md shadow-xs overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 bg-slate-50/60">
        <div className="flex items-center gap-3">
          <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
            Manager Review & Authorization Inbox
          </span>
          <div className="flex rounded-sm border border-slate-200 bg-white p-0.5">
            {FILTERS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => onFilter(option)}
                aria-pressed={filter === option}
                className={`px-3 py-1 text-xs font-medium rounded-xs transition-colors ${
                  filter === option
                    ? "bg-[#0070F2] text-white"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {option}
              </button>
            ))}
          </div>
          <span className="text-xs font-bold text-amber-700 bg-amber-50 px-2.5 py-0.5 rounded-full border border-amber-200">
            {pending} Pending Review
          </span>
        </div>

        <Button size="sm" variant="outline" onClick={onRefresh} disabled={loading}>
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} aria-hidden />
          Refresh Inbox
        </Button>
      </div>

      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 px-4 py-16 text-center">
          <ShieldCheck className="h-8 w-8 text-slate-300" aria-hidden />
          <div className="text-sm font-semibold text-slate-700">No approval requests in this view</div>
          <div className="max-w-md text-xs text-slate-500">
            During a customer call, if the customer requests a price modification, discount, or address change, it automatically pauses and appears in this manager inbox for review.
          </div>
        </div>
      ) : (
        <div className="grid gap-4 p-4 lg:grid-cols-2">
          {filtered.map((approval) => {
            const entries = Object.entries(approval.proposed_arguments).slice(0, 4);
            return (
              <article
                key={approval.id}
                className="flex flex-col justify-between gap-3 bg-white border border-slate-200 rounded-md p-4 shadow-xs hover:border-[#0070F2] transition-colors"
              >
                <div>
                  <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2 mb-2">
                    <span className="font-mono text-xs font-bold text-slate-900">
                      {approval.order_reference ?? shortId(approval.order_id)}
                    </span>
                    <StatusPill status={approval.status} />
                  </div>
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-xs font-bold text-[#0070F2]">
                      {humanize(approval.tool_name)}
                    </span>
                    <span className="text-[11px] text-slate-400">
                      &bull; {formatDateTime(approval.created_at)}
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 mb-3 bg-slate-50 p-2 rounded border border-slate-100">
                    {approval.reason}
                  </p>
                  <div className="space-y-1">
                    {entries.map(([k, v]) => (
                      <div key={k} className="flex justify-between text-[11px]">
                        <span className="text-slate-500">{humanize(k)}:</span>
                        <span className="font-mono font-semibold text-slate-800">
                          {previewValue(k, v)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="pt-2 border-t border-slate-100 flex justify-end">
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => onOpen(approval.id)}
                    className="flex items-center gap-1.5"
                  >
                    <span>Review & Authorize</span>
                    <ArrowUpRight className="h-3.5 w-3.5" />
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
