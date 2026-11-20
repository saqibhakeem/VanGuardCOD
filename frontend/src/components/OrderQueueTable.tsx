import { Inbox, MapPin, PhoneOutgoing, Plus, RefreshCw, Search } from "lucide-react";
import { useMemo, useState } from "react";

import type { Order, OrderStatus } from "../types";
import { formatMoney } from "../lib/format";
import { RtoRiskBar } from "./RtoRiskBar";
import { StatusPill } from "./StatusPill";
import { Button, INPUT_CLASS, SELECT_CLASS } from "./ui";

const STATUS_OPTIONS: Array<OrderStatus | "ALL"> = [
  "ALL",
  "PENDING_CALL",
  "CALLING",
  "VERIFIED",
  "NEEDS_APPROVAL",
  "RESCHEDULED",
  "CANCELLED",
];

interface Props {
  orders: Order[];
  loading: boolean;
  selectedOrderId: string | null;
  activeOrderId: string | null;
  triggeringOrderId: string | null;
  callActive: boolean;
  onSelect: (order: Order) => void;
  onTrigger: (order: Order) => void;
  onRefresh: () => void;
  onOpenWebhook: () => void;
}

export function OrderQueueTable({
  orders,
  loading,
  selectedOrderId,
  activeOrderId,
  triggeringOrderId,
  callActive,
  onSelect,
  onTrigger,
  onRefresh,
  onOpenWebhook,
}: Props) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<OrderStatus | "ALL">("ALL");

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return orders.filter((order) => {
      if (status !== "ALL" && order.status !== status) return false;
      if (!needle) return true;
      return [
        order.external_order_id,
        order.customer_name,
        order.customer_phone,
        order.raw_address,
        order.items_summary,
      ]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [orders, search, status]);

  return (
    <section className="border border-line bg-panel">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2.5">
        <div className="relative min-w-[180px] flex-1">
          <Search
            className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-3"
            aria-hidden
          />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search reference, buyer, phone, address"
            aria-label="Search orders"
            className={`${INPUT_CLASS} pl-7`}
          />
        </div>
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as OrderStatus | "ALL")}
          aria-label="Filter orders by status"
          className={`${SELECT_CLASS} w-[150px]`}
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option === "ALL" ? "All statuses" : option.replaceAll("_", " ")}
            </option>
          ))}
        </select>
        <Button size="sm" onClick={onRefresh} disabled={loading}>
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} aria-hidden />
          Refresh
        </Button>
        <Button size="sm" variant="primary" onClick={onOpenWebhook}>
          <Plus className="h-3.5 w-3.5" aria-hidden />
          Inject order
        </Button>
        <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.08em] text-ink-3">
          {filtered.length} of {orders.length}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[1040px] border-collapse text-left">
          <thead>
            <tr className="border-b border-line bg-panel-2/40 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
              <th className="px-3 py-2 font-medium">Order ref</th>
              <th className="px-3 py-2 font-medium">Customer and phone</th>
              <th className="px-3 py-2 font-medium">COD amount</th>
              <th className="px-3 py-2 font-medium">Address and landmark</th>
              <th className="px-3 py-2 font-medium">RTO risk</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 text-right font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((order) => {
              const selected = order.id === selectedOrderId;
              const active = order.id === activeOrderId;
              const busy = triggeringOrderId === order.id;
              return (
                <tr
                  key={order.id}
                  onClick={() => onSelect(order)}
                  className={`cursor-pointer border-b border-line/70 text-[12px] transition-colors hover:bg-panel-2/70 ${
                    selected ? "bg-panel-2/80" : ""
                  }`}
                >
                  <td
                    className={`px-3 py-2.5 align-top ${
                      selected ? "border-l-2 border-accent" : "border-l-2 border-transparent"
                    }`}
                  >
                    <div className="font-mono text-[12px] text-ink">
                      {order.external_order_id}
                    </div>
                    <div className="mt-0.5 max-w-[180px] truncate text-[10px] text-ink-3">
                      {order.items_summary}
                    </div>
                    {active ? (
                      <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.08em] text-accent">
                        In softphone
                      </div>
                    ) : null}
                  </td>
                  <td className="px-3 py-2.5 align-top">
                    <div className="text-ink">{order.customer_name}</div>
                    <div className="mt-0.5 font-mono text-[11px] text-ink-2">
                      {order.customer_phone}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5 align-top font-mono text-[12px] text-ink">
                    {formatMoney(order.cod_amount)}
                  </td>
                  <td className="max-w-[280px] px-3 py-2.5 align-top">
                    <div className="truncate text-ink-2" title={order.raw_address}>
                      {order.raw_address}
                    </div>
                    <div className="mt-1 flex items-center gap-1 text-[10px] text-ink-3">
                      <MapPin className="h-3 w-3 shrink-0" aria-hidden />
                      <span className="truncate">
                        {order.verified_landmark
                          ? `Landmark: ${order.verified_landmark}`
                          : "No verified landmark"}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 align-top">
                    <RtoRiskBar score={order.rto_risk_score} />
                  </td>
                  <td className="px-3 py-2.5 align-top">
                    <StatusPill status={order.status} />
                    {order.delivery_window ? (
                      <div className="mt-1 max-w-[140px] truncate text-[10px] text-ink-3">
                        {order.delivery_window}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-3 py-2.5 text-right align-top">
                    <Button
                      size="sm"
                      variant="primary"
                      disabled={callActive || busy || order.status === "CANCELLED"}
                      onClick={(event) => {
                        event.stopPropagation();
                        onTrigger(order);
                      }}
                      title={
                        callActive
                          ? "Hang up the current call before triggering another"
                          : "Trigger outbound verification call"
                      }
                    >
                      <PhoneOutgoing
                        className={`h-3.5 w-3.5 ${busy ? "animate-pulse" : ""}`}
                        aria-hidden
                      />
                      {busy ? "Dialing" : "Call"}
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 px-4 py-14 text-center">
            <Inbox className="h-6 w-6 text-ink-3" aria-hidden />
            <div className="text-[13px] text-ink-2">No orders match this view</div>
            <div className="max-w-sm text-[11px] text-ink-3">
              Clear the filters or inject a test COD order through the webhook simulator.
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
