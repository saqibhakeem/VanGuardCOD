import {
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Globe,
  RefreshCw,
  ShoppingBag,
  Sparkles,
} from "lucide-react";
import { useState } from "react";

import { api } from "../api";
import type { IngestResponse, Order } from "../types";
import { StatusPill } from "./StatusPill";
import { Button, INPUT_CLASS } from "./ui";


interface Props {
  orders: Order[];
  onOrderCreated: (response: IngestResponse) => void;
  onRefresh: () => void;
}

export function StoreAndSheetsView({ orders, onOrderCreated, onRefresh }: Props) {
  const [customerName, setCustomerName] = useState("Ayesha Siddiqui");
  const [customerPhone, setCustomerPhone] = useState("+923015554321");
  const [itemsSummary, setItemsSummary] = useState("2x Embroidered Lawn Suit");
  const [codAmount, setCodAmount] = useState("14500");
  const [rawAddress, setRawAddress] = useState(
    "Apartment 402, Block B, DHA Phase 5, Karachi",
  );
  const [deliveryWindow, setDeliveryWindow] = useState("Tomorrow 4 PM to 7 PM");
  const [submitting, setSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handlePlaceStoreOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setSubmitSuccess(null);
    setSubmitError(null);

    const amount = Number(codAmount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setSubmitError("Please enter a valid COD amount.");
      setSubmitting(false);
      return;
    }

    try {
      const orderRef = `ORD-${String(Date.now()).slice(-5)}`;
      const res = await api.ingestOrder({
        external_order_id: orderRef,
        customer_name: customerName.trim(),
        customer_phone: customerPhone.trim(),
        items_summary: itemsSummary.trim(),
        cod_amount: amount,
        raw_address: rawAddress.trim(),
        delivery_window: deliveryWindow.trim() || null,
      });

      setSubmitSuccess(
        `Order ${res.order.external_order_id} placed! Autonomous call session queued. The customer phone is now ringing!`,
      );
      onOrderCreated(res);
      // Auto trigger call immediately
      await api.triggerOutbound(res.order.id);
      onRefresh();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to place order.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleExportCsv = () => {
    const headers = [
      "Order ID",
      "Customer",
      "Phone",
      "Items",
      "COD Amount",
      "Address",
      "Landmark",
      "RTO Score",
      "Status",
      "Created At",
    ];
    const rows = orders.map((o) => [
      o.external_order_id,
      `"${o.customer_name}"`,
      o.customer_phone,
      `"${o.items_summary}"`,
      o.cod_amount,
      `"${o.raw_address}"`,
      `"${o.verified_landmark ?? ""}"`,
      o.rto_risk_score,
      o.status,
      o.created_at,
    ]);

    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `VanguardCOD_Orders_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      {/* Top Banner explaining the Store & Sheet loop */}
      <div className="bg-white border border-slate-200 rounded-md p-5 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold text-[#0070F2] uppercase tracking-wider mb-1">
            <Globe className="h-4 w-4" />
            End-to-End E-Commerce & Google Sheets Integration
          </div>
          <h2 className="text-base font-bold text-slate-900">
            Automated Store Checkout to Voice Call Verification
          </h2>
          <p className="text-xs text-slate-500 mt-0.5 max-w-2xl">
            Orders placed on your Shopify, WooCommerce, or custom order form instantly webhook into VanguardCOD.
            The AI voice agent calls the buyer to verify address & landmark, and writes back the confirmed details to your VanguardCOD database and connected Google Sheet.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button variant="outline" size="sm" onClick={onRefresh}>
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh Sheet
          </Button>
          <Button variant="primary" size="sm" onClick={handleExportCsv}>
            <Download className="h-3.5 w-3.5" />
            Export to CSV
          </Button>
        </div>
      </div>

      {/* Grid: Left = Web Store Checkout, Right = Google Sheet Live View */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* LEFT: E-COMMERCE ORDER FORM SIMULATOR */}
        <div className="lg:col-span-5 bg-white border border-slate-200 rounded-md shadow-xs p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
              <div className="flex items-center gap-2">
                <div className="p-1.5 bg-blue-50 text-[#0070F2] rounded-sm">
                  <ShoppingBag className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-800">
                    Store Order Form Simulator
                  </h3>
                  <p className="text-[11px] text-slate-500">
                    Simulate customer checkout on your website
                  </p>
                </div>
              </div>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                Live Webhook
              </span>
            </div>

            {submitSuccess ? (
              <div className="mb-4 p-3 bg-emerald-50 border border-emerald-200 rounded-sm text-xs text-emerald-800 flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0 mt-0.5" />
                <span>{submitSuccess}</span>
              </div>
            ) : null}

            {submitError ? (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-sm text-xs text-red-800">
                {submitError}
              </div>
            ) : null}

            <form onSubmit={handlePlaceStoreOrder} className="space-y-3">
              <div>
                <label className="block text-[11px] font-medium text-slate-700 mb-1">
                  Customer Full Name
                </label>
                <input
                  type="text"
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                  className={INPUT_CLASS}
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-medium text-slate-700 mb-1">
                    Customer Phone (E.164)
                  </label>
                  <input
                    type="text"
                    value={customerPhone}
                    onChange={(e) => setCustomerPhone(e.target.value)}
                    className={INPUT_CLASS}
                    required
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-700 mb-1">
                    COD Amount (PKR)
                  </label>
                  <input
                    type="number"
                    value={codAmount}
                    onChange={(e) => setCodAmount(e.target.value)}
                    className={INPUT_CLASS}
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-700 mb-1">
                  Items Description
                </label>
                <input
                  type="text"
                  value={itemsSummary}
                  onChange={(e) => setItemsSummary(e.target.value)}
                  className={INPUT_CLASS}
                  required
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-700 mb-1">
                  Shipping Delivery Address
                </label>
                <textarea
                  value={rawAddress}
                  onChange={(e) => setRawAddress(e.target.value)}
                  rows={2}
                  className={INPUT_CLASS}
                  required
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-700 mb-1">
                  Preferred Delivery Slot
                </label>
                <input
                  type="text"
                  value={deliveryWindow}
                  onChange={(e) => setDeliveryWindow(e.target.value)}
                  className={INPUT_CLASS}
                />
              </div>

              <div className="pt-2">
                <Button
                  type="submit"
                  variant="primary"
                  disabled={submitting}
                  className="w-full py-2.5 font-bold flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white"
                >
                  <Sparkles className="h-4 w-4" />
                  {submitting ? "Placing Order & Ringing Phone..." : "Place COD Order & Ring Customer Phone"}
                </Button>
              </div>
            </form>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-100 text-[11px] text-slate-500 flex items-center justify-between">
            <span>Webhook endpoint: <code>/api/v1/webhooks/orders</code></span>
            <span className="text-emerald-600 font-medium">100% Automated</span>
          </div>
        </div>

        {/* RIGHT: LIVE GOOGLE SHEETS SPREADSHEET VIEW */}
        <div className="lg:col-span-7 bg-white border border-slate-200 rounded-md shadow-xs overflow-hidden flex flex-col">
          {/* Google Sheets Header Bar */}
          <div className="bg-[#0F9D58] text-white px-4 py-2.5 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <FileSpreadsheet className="h-5 w-5" />
              <div>
                <div className="text-xs font-bold leading-tight flex items-center gap-2">
                  <span>VanguardCOD_Orders_Master_Sync.gsheet</span>
                  <span className="text-[10px] bg-white/20 px-1.5 py-0.5 rounded font-normal">
                    Shared with Logistics Team
                  </span>
                </div>
                <div className="text-[10px] text-emerald-100">
                  Last automated sync: Just now &bull; {orders.length} rows updated
                </div>
              </div>
            </div>

            <span className="text-[11px] font-medium bg-emerald-700 px-2.5 py-1 rounded-sm border border-emerald-600 flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-white animate-pulse" />
              Live Connected
            </span>
          </div>

          {/* Spreadsheet Table */}
          <div className="flex-1 overflow-x-auto min-h-[360px]">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-100 border-b border-slate-200 font-semibold text-slate-600 text-[11px]">
                  <th className="py-2 px-3 border-r border-slate-200 w-10 text-center text-slate-400">#</th>
                  <th className="py-2 px-3 border-r border-slate-200">Order ID</th>
                  <th className="py-2 px-3 border-r border-slate-200">Customer</th>
                  <th className="py-2 px-3 border-r border-slate-200">Phone</th>
                  <th className="py-2 px-3 border-r border-slate-200">COD (PKR)</th>
                  <th className="py-2 px-3 border-r border-slate-200">Status</th>
                  <th className="py-2 px-3 border-r border-slate-200">Verified Landmark</th>
                  <th className="py-2 px-3">RTO Risk</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-sans">
                {orders.map((order, idx) => (
                  <tr
                    key={order.id}
                    className="hover:bg-blue-50/40 transition-colors text-slate-700 text-[11px]"
                  >
                    <td className="py-2 px-3 border-r border-slate-100 text-center font-mono text-slate-400">
                      {idx + 1}
                    </td>
                    <td className="py-2 px-3 border-r border-slate-100 font-mono font-medium text-slate-900">
                      {order.external_order_id}
                    </td>
                    <td className="py-2 px-3 border-r border-slate-100 font-medium">
                      {order.customer_name}
                    </td>
                    <td className="py-2 px-3 border-r border-slate-100 font-mono text-slate-600">
                      {order.customer_phone}
                    </td>
                    <td className="py-2 px-3 border-r border-slate-100 font-mono text-right font-medium">
                      {order.cod_amount.toLocaleString()}
                    </td>
                    <td className="py-2 px-3 border-r border-slate-100">
                      <StatusPill status={order.status} />
                    </td>
                    <td className="py-2 px-3 border-r border-slate-100 text-slate-800">
                      {order.verified_landmark ? (
                        <span className="font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded">
                          {order.verified_landmark}
                        </span>
                      ) : (
                        <span className="text-slate-400 italic">Pending call</span>
                      )}
                    </td>
                    <td className="py-2 px-3 font-mono">
                      <span
                        className={`font-bold ${
                          order.rto_risk_score >= 50
                            ? "text-red-600"
                            : "text-emerald-600"
                        }`}
                      >
                        {order.rto_risk_score}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="bg-slate-50 border-t border-slate-200 px-4 py-2 text-[11px] text-slate-500 flex items-center justify-between">
            <span>Formula: <code>=VANGUARD_VERIFY(ORDER_ID, CUSTOMER_PHONE)</code></span>
            <span>Two-way Google Sheets Sync Enabled</span>
          </div>
        </div>
      </div>
    </div>
  );
}
