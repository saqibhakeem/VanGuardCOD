import { Check, ShieldCheck, X, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { Approval } from "../types";
import {
  formatDateTime,
  formatMoney,
  humanize,
  shortId,
  TONE_TEXT,
} from "../lib/format";
import { StatusPill } from "./StatusPill";
import { Button, INPUT_CLASS, SectionLabel } from "./ui";

interface Props {
  open: boolean;
  approvals: Approval[];
  selectedId: string | null;
  onSelect: (approvalId: string) => void;
  onClose: () => void;
  onResolve: (approval: Approval, approved: boolean, note: string) => Promise<void>;
  busyId: string | null;
  error: string | null;
}

const LABELS: Record<string, string> = {
  raw_address: "Address",
  cod_amount: "COD amount",
  delivery_window: "Delivery window",
  verified_landmark: "Landmark",
  status: "Order status",
  order_id: "Order",
  rider_note: "Rider note",
  attempt_outcome: "Attempt outcome",
};

function displayValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (key === "cod_amount" && typeof value === "number") return formatMoney(value);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function ApprovalDrawer({
  open,
  approvals,
  selectedId,
  onSelect,
  onClose,
  onResolve,
  busyId,
  error,
}: Props) {
  const [note, setNote] = useState("");
  const selected = approvals.find((item) => item.id === selectedId) ?? approvals[0] ?? null;

  useEffect(() => {
    setNote("");
  }, [selectedId]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, open]);

  const proposedKeys = useMemo(() => {
    if (!selected) return [];
    const keys = new Set([
      ...Object.keys(selected.current_values),
      ...Object.keys(selected.proposed_arguments),
    ]);
    return Array.from(keys).sort();
  }, [selected]);

  if (!open) return null;

  const pending = approvals.filter((approval) => approval.status === "PENDING");
  const busy = selected ? busyId === selected.id : false;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/70">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Approval gate drawer"
        className="flex h-full w-full max-w-3xl flex-col border-l border-line bg-panel shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-warning" aria-hidden />
            <div>
              <div className="text-[13px] font-semibold">HITL approval gate</div>
              <div className="font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
                {pending.length} pending | review before mutation
              </div>
            </div>
          </div>
          <Button size="sm" variant="ghost" onClick={onClose} aria-label="Close approval drawer">
            <X className="h-4 w-4" aria-hidden />
          </Button>
        </div>

        {approvals.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center">
            <ShieldCheck className="h-7 w-7 text-ink-3" aria-hidden />
            <div className="text-[13px] text-ink-2">No approvals in this view</div>
            <div className="max-w-xs text-[11px] text-ink-3">
              High value COD revisions and address reroutes pause here before the agent can mutate
              an order.
            </div>
          </div>
        ) : (
          <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[260px_1fr]">
            <div className="min-h-0 overflow-y-auto border-b border-line lg:border-b-0 lg:border-r">
              {approvals.map((approval) => {
                const active = selected?.id === approval.id;
                return (
                  <button
                    key={approval.id}
                    type="button"
                    onClick={() => onSelect(approval.id)}
                    className={`flex w-full flex-col gap-1 border-b border-line px-3 py-2.5 text-left transition-colors ${
                      active ? "bg-panel-2" : "hover:bg-panel-2/60"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[11px] text-ink">
                        {approval.order_reference ?? shortId(approval.order_id)}
                      </span>
                      <StatusPill status={approval.status} />
                    </div>
                    <span className="truncate text-[11px] text-ink-2">
                      {approval.tool_name}
                    </span>
                    <span className="line-clamp-2 text-[10px] leading-4 text-ink-3">
                      {approval.reason}
                    </span>
                  </button>
                );
              })}
            </div>

            {selected ? (
              <div className="flex min-h-0 flex-col overflow-y-auto">
                <div className="border-b border-line px-4 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-3">
                        {humanize(selected.tool_name)}
                      </div>
                      <div className="mt-0.5 text-[15px] font-semibold">
                        {selected.order_reference ?? shortId(selected.order_id)}
                      </div>
                    </div>
                    <StatusPill status={selected.status} />
                  </div>
                  <div className="mt-2 text-[11px] leading-4 text-ink-2">{selected.reason}</div>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
                    <span>created {formatDateTime(selected.created_at)}</span>
                    <span>session {shortId(selected.call_session_id)}</span>
                    <span>approval {shortId(selected.id)}</span>
                  </div>
                </div>

                <div className="border-b border-line px-4 py-3">
                  <SectionLabel className="mb-2">Proposed mutation diff</SectionLabel>
                  <div className="border border-line">
                    <div className="grid grid-cols-[110px_1fr_1fr] gap-px bg-line font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
                      <div className="bg-panel-2 px-2 py-1.5">Field</div>
                      <div className="bg-panel-2 px-2 py-1.5">Current</div>
                      <div className="bg-panel-2 px-2 py-1.5">Proposed</div>
                    </div>
                    {proposedKeys.map((key) => {
                      const current = selected.current_values[key];
                      const proposed = selected.proposed_arguments[key];
                      const changed = String(current) !== String(proposed);
                      return (
                        <div
                          key={key}
                          className={`grid grid-cols-[110px_1fr_1fr] gap-px border-t border-line bg-line text-[11px] ${
                            changed ? "bg-warning/5" : ""
                          }`}
                        >
                          <div className="bg-panel px-2 py-1.5 font-mono text-[10px] text-ink-3">
                            {LABELS[key] ?? key}
                          </div>
                          <div className="break-words bg-panel px-2 py-1.5 text-ink-2">
                            {displayValue(key, current)}
                          </div>
                          <div
                            className={`break-words bg-panel px-2 py-1.5 ${
                              changed ? TONE_TEXT.warning : "text-ink-2"
                            }`}
                          >
                            {displayValue(key, proposed)}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {error ? (
                  <div className="mx-4 mt-3 border border-critical/40 bg-critical/10 px-3 py-2 text-[11px] text-critical">
                    {error}
                  </div>
                ) : null}

                {selected.status === "PENDING" ? (
                  <div className="mt-auto border-t border-line px-4 py-3">
                    <SectionLabel className="mb-1.5">Operator note</SectionLabel>
                    <textarea
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                      rows={2}
                      placeholder="Optional note stored in the call transcript"
                      className={`${INPUT_CLASS} resize-none`}
                    />
                    <div className="mt-2 flex flex-wrap justify-end gap-2">
                      <Button
                        variant="danger"
                        disabled={busy}
                        onClick={() => void onResolve(selected, false, note)}
                      >
                        <XCircle className="h-3.5 w-3.5" aria-hidden />
                        {busy ? "Working" : "Reject"}
                      </Button>
                      <Button
                        variant="primary"
                        disabled={busy}
                        onClick={() => void onResolve(selected, true, note)}
                      >
                        <Check className="h-3.5 w-3.5" aria-hidden />
                        {busy ? "Working" : "Approve"}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="mt-auto border-t border-line px-4 py-3 font-mono text-[10px] uppercase tracking-[0.08em] text-ink-3">
                    This request is already resolved.
                  </div>
                )}
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
