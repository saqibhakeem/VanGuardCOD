import { ArrowRight, Check, PhoneOutgoing, Webhook, X } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api";
import type { IngestResponse, Order } from "../types";
import { formatMoney } from "../lib/format";
import { RtoRiskBar } from "./RtoRiskBar";
import { Button, Field, INPUT_CLASS } from "./ui";

interface Props {
  open: boolean;
  onClose: () => void;
  onIngested: (result: IngestResponse) => void;
  onCallOrder: (order: Order) => void;
  callActive: boolean;
}

interface FormState {
  external_order_id: string;
  customer_name: string;
  customer_phone: string;
  items_summary: string;
  cod_amount: string;
  raw_address: string;
  delivery_window: string;
}

function defaultForm(): FormState {
  return {
    external_order_id: `ORD-${String(Date.now()).slice(-6)}`,
    customer_name: "Sana Malik",
    customer_phone: "0301 234 5678",
    items_summary: "2x Cotton Kurti, 1x Lawn Dupatta",
    cod_amount: "18000",
    raw_address: "House 12, Street 4, Block C, North Nazimabad, Karachi",
    delivery_window: "Tomorrow 5 PM",
  };
}

export function WebhookSimulatorModal({
  open,
  onClose,
  onIngested,
  onCallOrder,
  callActive,
}: Props) {
  const [form, setForm] = useState<FormState>(defaultForm);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IngestResponse | null>(null);

  useEffect(() => {
    if (open) {
      setForm(defaultForm());
      setError(null);
      setResult(null);
      setBusy(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, open]);

  if (!open) return null;

  const update = (key: keyof FormState) => (value: string) =>
    setForm((previous) => ({ ...previous, [key]: value }));

  const submit = async () => {
    const amount = Number(form.cod_amount);
    if (!form.external_order_id.trim() || !form.customer_name.trim()) {
      setError("Order reference and customer name are required.");
      return;
    }
    if (!form.customer_phone.trim() || !form.raw_address.trim()) {
      setError("Phone number and address are required.");
      return;
    }
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("COD amount must be a positive number.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await api.ingestOrder({
        external_order_id: form.external_order_id.trim(),
        customer_name: form.customer_name.trim(),
        customer_phone: form.customer_phone.trim(),
        items_summary: form.items_summary.trim(),
        cod_amount: amount,
        raw_address: form.raw_address.trim(),
        delivery_window: form.delivery_window.trim() || null,
      });
      setResult(response);
      onIngested(response);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : String(submitError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Webhook simulator"
        className="flex max-h-[92vh] w-full max-w-2xl flex-col border border-line bg-panel shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div className="flex items-center gap-2">
            <Webhook className="h-4 w-4 text-accent" aria-hidden />
            <div>
              <div className="text-[13px] font-semibold">Webhook simulator</div>
              <div className="font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
                POST /api/v1/webhooks/orders
              </div>
            </div>
          </div>
          <Button size="sm" variant="ghost" onClick={onClose} aria-label="Close webhook simulator">
            <X className="h-4 w-4" aria-hidden />
          </Button>
        </div>

        {result ? (
          <div className="flex flex-col gap-4 overflow-y-auto px-4 py-4">
            <div className="flex items-center gap-2 border border-verified/40 bg-verified/10 px-3 py-2 text-[12px] text-verified">
              <Check className="h-4 w-4" aria-hidden />
              Order ingested and queued for outbound verification.
            </div>

            <div className="grid gap-px border border-line bg-line sm:grid-cols-2">
              <div className="bg-panel px-3 py-2.5">
                <div className="font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
                  Order
                </div>
                <div className="mt-1 font-mono text-[13px]">{result.order.external_order_id}</div>
                <div className="text-[11px] text-ink-2">
                  {result.order.customer_name} | {formatMoney(result.order.cod_amount)}
                </div>
              </div>
              <div className="bg-panel px-3 py-2.5">
                <div className="font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
                  Queued session
                </div>
                <div className="mt-1 font-mono text-[11px] text-ink-2">{result.session_id}</div>
                <div className="text-[11px] text-ink-3">{result.call_session.status}</div>
              </div>
            </div>

            <div className="border border-line bg-panel-2 px-3 py-3">
              <div className="flex items-center justify-between">
                <span className="font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
                  Deterministic RTO score
                </span>
                <RtoRiskBar score={result.rto.score} />
              </div>
              <div className="mt-2 grid gap-1 text-[11px] text-ink-2 sm:grid-cols-2">
                <div>
                  House number detected:{" "}
                  <span className="font-mono text-ink">
                    {result.rto.has_house_number ? "yes" : "no"}
                  </span>
                </div>
                <div>
                  Address words:{" "}
                  <span className="font-mono text-ink">{result.rto.address_word_count}</span>
                </div>
                <div className="sm:col-span-2">
                  Missing components:{" "}
                  <span className="font-mono text-ink">
                    {result.rto.missing_components.length
                      ? result.rto.missing_components.join(", ")
                      : "none"}
                  </span>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line pt-3">
              <Button onClick={onClose}>Close</Button>
              <Button
                variant="primary"
                disabled={callActive}
                onClick={() => {
                  onCallOrder(result.order);
                  onClose();
                }}
              >
                <PhoneOutgoing className="h-3.5 w-3.5" aria-hidden />
                Call this order
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div className="grid gap-3 overflow-y-auto px-4 py-4 sm:grid-cols-2">
              <Field label="External order reference">
                <input
                  value={form.external_order_id}
                  onChange={(event) => update("external_order_id")(event.target.value)}
                  className={INPUT_CLASS}
                />
              </Field>
              <Field label="Customer name">
                <input
                  value={form.customer_name}
                  onChange={(event) => update("customer_name")(event.target.value)}
                  className={INPUT_CLASS}
                />
              </Field>
              <Field label="Customer phone" hint="Local or E.164 format is normalized on ingest.">
                <input
                  value={form.customer_phone}
                  onChange={(event) => update("customer_phone")(event.target.value)}
                  className={INPUT_CLASS}
                />
              </Field>
              <Field label="COD amount (PKR)">
                <input
                  value={form.cod_amount}
                  inputMode="decimal"
                  onChange={(event) => update("cod_amount")(event.target.value)}
                  className={`${INPUT_CLASS} font-mono`}
                />
              </Field>
              <div className="sm:col-span-2">
                <Field label="Items summary">
                  <input
                    value={form.items_summary}
                    onChange={(event) => update("items_summary")(event.target.value)}
                    className={INPUT_CLASS}
                  />
                </Field>
              </div>
              <div className="sm:col-span-2">
                <Field label="Raw shipping address">
                  <textarea
                    value={form.raw_address}
                    onChange={(event) => update("raw_address")(event.target.value)}
                    rows={2}
                    className={`${INPUT_CLASS} resize-none`}
                  />
                </Field>
              </div>
              <Field label="Delivery window" hint="Optional, spoken back by the agent.">
                <input
                  value={form.delivery_window}
                  onChange={(event) => update("delivery_window")(event.target.value)}
                  className={INPUT_CLASS}
                />
              </Field>
            </div>

            {error ? (
              <div className="mx-4 mb-2 border border-critical/40 bg-critical/10 px-3 py-2 text-[11px] text-critical">
                {error}
              </div>
            ) : null}

            <div className="flex items-center justify-between gap-2 border-t border-line px-4 py-3">
              <span className="font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
                Risk score is computed before the call
              </span>
              <div className="flex gap-2">
                <Button onClick={onClose}>Cancel</Button>
                <Button variant="primary" onClick={submit} disabled={busy}>
                  {busy ? "Ingesting" : "Ingest order"}
                  <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
