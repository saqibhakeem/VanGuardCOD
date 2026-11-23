import {
  Clock,
  Inbox,
  MapPin,
  MessageSquare,
  PhoneCall,
  PhoneOutgoing,
  Plus,
  RefreshCw,
  Search,
} from "lucide-react";
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
  "PENDING_RETRY",
  "VERIFIED",
  "NEEDS_APPROVAL",
  "RESCHEDULED",
  "FAILED_CONTACT",
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
  onTrigger: (order: Order, channel?: string) => void;
  onRetry?: (order: Order, channel?: string) => void;
  onDispatchRetries?: () => void;
  dispatchingRetries?: boolean;
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
  onRetry,
  onDispatchRetries,
  dispatchingRetries = false,
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
    <section className="border border-slate-200 bg-white rounded-md shadow-xs overflow-hidden">
      {/* Top Filter and Action Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 bg-slate-50/60">
        <div className="flex items-center gap-3 flex-1 min-w-[280px]">
          <div className="relative flex-1 max-w-sm">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400"
              aria-hidden
            />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search by order ID, customer name, phone, address..."
              aria-label="Search orders"
              className={`${INPUT_CLASS} pl-9`}
            />
          </div>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as OrderStatus | "ALL")}
            aria-label="Filter orders by status"
            className={`${SELECT_CLASS} w-[160px]`}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option === "ALL" ? "All Statuses" : option.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          {onDispatchRetries ? (
            <Button
              size="sm"
              variant="outline"
              onClick={onDispatchRetries}
              disabled={dispatchingRetries || loading}
              className="border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100 font-medium"
              title="Batch dispatch any orders waiting for automated retry"
            >
              <Clock className={`h-3.5 w-3.5 text-amber-600 ${dispatchingRetries ? "animate-spin" : ""}`} aria-hidden />
              Dispatch Retries
            </Button>
          ) : null}
          <Button size="sm" variant="outline" onClick={onRefresh} disabled={loading}>
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} aria-hidden />
            Refresh
          </Button>
          <Button size="sm" variant="primary" onClick={onOpenWebhook}>
            <Plus className="h-3.5 w-3.5" aria-hidden />
            Add Test Order
          </Button>
          <span className="text-xs font-medium text-slate-500 pl-2 border-l border-slate-200">
            {filtered.length} of {orders.length} orders
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[1040px] border-collapse text-left">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-600">
              <th className="px-4 py-3">Order ID</th>
              <th className="px-4 py-3">Customer & Contact</th>
              <th className="px-4 py-3">COD Amount</th>
              <th className="px-4 py-3">Delivery Address & Landmark</th>
              <th className="px-4 py-3">RTO Risk</th>
              <th className="px-4 py-3">Verification Status</th>
              <th className="px-4 py-3 text-right">Autonomous Call</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.map((order) => {
              const selected = order.id === selectedOrderId;
              const active = order.id === activeOrderId;
              const busy = triggeringOrderId === order.id;
              return (
                <tr
                  key={order.id}
                  onClick={() => onSelect(order)}
                  className={`cursor-pointer text-[12px] transition-colors hover:bg-blue-50/40 ${
                    selected ? "bg-blue-50/60 font-medium" : ""
                  }`}
                >
                  <td className="px-4 py-3 align-top">
                    <div className="font-mono font-semibold text-slate-900">
                      {order.external_order_id}
                    </div>
                    <div className="mt-0.5 max-w-[180px] truncate text-[11px] text-slate-500">
                      {order.items_summary}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-1">
                      {order.verification_channel === "WHATSAPP" ? (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <MessageSquare className="h-3 w-3" /> WhatsApp
                        </span>
                      ) : order.verification_channel === "PHONE_CALL" ? (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                          <PhoneCall className="h-3 w-3" /> Twilio Voice
                        </span>
                      ) : null}
                      {order.delivery_status ? (
                        <span className="text-[10px] text-slate-400 capitalize">
                          &bull; {order.delivery_status}
                        </span>
                      ) : null}
                    </div>
                    {active ? (
                      <span className="inline-block mt-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-[#0070F2]">
                        In Call Session
                      </span>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <div className="font-semibold text-slate-900">{order.customer_name}</div>
                    <div className="mt-0.5 font-mono text-[11px] text-slate-500">
                      {order.customer_phone}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 align-top font-mono font-semibold text-slate-900">
                    {formatMoney(order.cod_amount)}
                  </td>
                  <td className="max-w-[280px] px-4 py-3 align-top">
                    <div className="truncate text-slate-700" title={order.raw_address}>
                      {order.raw_address}
                    </div>
                    <div className="mt-1 flex items-center gap-1.5 text-[11px]">
                      <MapPin className="h-3.5 w-3.5 text-slate-400 shrink-0" aria-hidden />
                      <span className="truncate">
                        {order.verified_landmark ? (
                          <span className="font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                            {order.verified_landmark}
                          </span>
                        ) : (
                          <span className="text-slate-400 italic">No verified landmark yet</span>
                        )}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 align-top">
                    <RtoRiskBar score={order.rto_risk_score} />
                  </td>
                  <td className="px-4 py-3 align-top">
                    <StatusPill status={order.status} />
                    {order.status === "PENDING_RETRY" ? (
                      <div className="mt-1 flex items-center gap-1 text-[11px] font-medium text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
                        <Clock className="h-3 w-3 text-amber-600 shrink-0" />
                        <span>Attempt {order.call_attempts || 1}/3 &bull; Retry in 2h</span>
                      </div>
                    ) : null}
                    {order.status === "FAILED_CONTACT" ? (
                      <div className="mt-1 text-[10px] text-red-600 font-semibold">
                        {order.call_attempts || 3} calls unanswered
                      </div>
                    ) : null}
                    {order.delivery_window ? (
                      <div className="mt-1 max-w-[140px] truncate text-[10px] text-slate-500">
                        {order.delivery_window}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 text-right align-top">
                    {order.status === "PENDING_RETRY" ? (
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          size="sm"
                          variant="success"
                          disabled={callActive || busy}
                          onClick={(event) => {
                            event.stopPropagation();
                            if (onRetry) onRetry(order, "TWILIO");
                            else onTrigger(order, "TWILIO");
                          }}
                          title="Retry AI phone call immediately"
                          className="bg-amber-600 hover:bg-amber-700 text-white font-bold"
                        >
                          <PhoneOutgoing
                            className={`h-3.5 w-3.5 ${busy ? "animate-pulse" : ""}`}
                            aria-hidden
                          />
                          {busy ? "Dialing..." : "Retry Call"}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={callActive || busy}
                          onClick={(event) => {
                            event.stopPropagation();
                            if (onRetry) onRetry(order, "WHATSAPP");
                            else onTrigger(order, "WHATSAPP");
                          }}
                          title="Retry via WhatsApp chat agent"
                          className="border-emerald-300 text-emerald-700 hover:bg-emerald-50 px-2"
                        >
                          <MessageSquare className="h-3.5 w-3.5 text-emerald-600" />
                        </Button>
                      </div>
                    ) : (
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          size="sm"
                          variant={order.status === "VERIFIED" ? "outline" : "success"}
                          disabled={callActive || busy || order.status === "CANCELLED" || order.status === "FAILED_CONTACT"}
                          onClick={(event) => {
                            event.stopPropagation();
                            onTrigger(order);
                          }}
                          title={
                            callActive
                              ? "Hang up active call before triggering another"
                              : order.status === "FAILED_CONTACT"
                              ? "Customer uncontactable after maximum attempts"
                              : "Trigger outbound verification via configured channel"
                          }
                          className={
                            order.status === "VERIFIED"
                              ? ""
                              : order.status === "FAILED_CONTACT"
                              ? "opacity-50 cursor-not-allowed"
                              : "bg-blue-600 hover:bg-blue-700 text-white font-bold"
                          }
                        >
                          <PhoneOutgoing
                            className={`h-3.5 w-3.5 ${busy ? "animate-pulse" : ""}`}
                            aria-hidden
                          />
                          {busy
                            ? "Dispatching..."
                            : order.status === "VERIFIED"
                            ? "Re-verify"
                            : order.status === "FAILED_CONTACT"
                            ? "Failed Contact"
                            : "Verify Call"}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={callActive || busy || order.status === "CANCELLED" || order.status === "FAILED_CONTACT"}
                          onClick={(event) => {
                            event.stopPropagation();
                            onTrigger(order, "WHATSAPP");
                          }}
                          title="Trigger WhatsApp Conversational Chat Agent"
                          className="border-emerald-300 text-emerald-700 hover:bg-emerald-50 px-2"
                        >
                          <MessageSquare className="h-3.5 w-3.5 text-emerald-600" />
                          <span className="hidden xl:inline text-xs">WhatsApp</span>
                        </Button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 px-4 py-14 text-center">
            <Inbox className="h-8 w-8 text-slate-300" aria-hidden />
            <div className="text-sm font-semibold text-slate-700">No orders match this filter</div>
            <div className="max-w-sm text-xs text-slate-500">
              Clear your search filters or click &ldquo;Add Test Order&rdquo; above.
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

