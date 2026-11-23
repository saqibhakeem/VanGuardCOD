import {
  AlertCircle,
  CheckCircle2,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api, getTenantKey, setTenantKey } from "./api";
import { ApprovalDrawer } from "./components/ApprovalDrawer";
import { ApprovalGate } from "./components/ApprovalGate";
import { ConfigView } from "./components/ConfigView";
import { KpiStrip } from "./components/KpiStrip";
import { LoginView } from "./components/LoginView";
import { OrderQueueTable } from "./components/OrderQueueTable";
import { SaaSNavbar } from "./components/SaaSNavbar";
import { SessionsView } from "./components/SessionsView";
import { StoreAndSheetsView } from "./components/StoreAndSheetsView";
import { WebhookSimulatorModal } from "./components/WebhookSimulatorModal";
import type {
  Approval,
  ApprovalStatus,
  CallSessionSummary,
  IngestResponse,
  Order,
  RuntimeConfig,
  User,
  ViewKey,
} from "./types";

type ApprovalFilter = ApprovalStatus | "ALL";

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export default function App() {
  const [currentUser, setCurrentUser] = useState<User | null>(() => {
    try {
      const raw = window.localStorage.getItem("vanguardcod.user");
      if (raw) return JSON.parse(raw) as User;
      return null;
    } catch {
      return null;
    }
  });

  const [view, setView] = useState<ViewKey>(() => {
    try {
      const p = new URLSearchParams(window.location.search);
      const v = p.get("view") as ViewKey;
      if (v && ["operations", "sessions", "approvals", "integrations", "config"].includes(v)) {
        return v;
      }
    } catch {}
    return "operations";
  });
  const [apiKey] = useState(getTenantKey());
  const [orders, setOrders] = useState<Order[]>([]);
  const [sessions, setSessions] = useState<CallSessionSummary[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [dataError, setDataError] = useState<string | null>(null);

  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [triggeringOrderId, setTriggeringOrderId] = useState<string | null>(null);
  const [webhookOpen, setWebhookOpen] = useState(() => {
    try {
      return new URLSearchParams(window.location.search).get("modal") === "webhook";
    } catch {
      return false;
    }
  });
  const [approvalFilter, setApprovalFilter] = useState<ApprovalFilter>("PENDING");
  const [approvalDrawerOpen, setApprovalDrawerOpen] = useState(() => {
    try {
      return new URLSearchParams(window.location.search).get("modal") === "approval";
    } catch {
      return false;
    }
  });
  const [selectedApprovalId, setSelectedApprovalId] = useState<string | null>(null);
  const [approvalBusyId, setApprovalBusyId] = useState<string | null>(null);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [dispatchingRetries, setDispatchingRetries] = useState(false);
  const [toast, setToast] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const refresh = useCallback(async (spinner = false) => {
    if (spinner) setLoading(true);
    setRefreshing(true);
    const [ordersResult, sessionsResult, approvalsResult, configResult] =
      await Promise.allSettled([
        api.orders(),
        api.sessions(),
        api.approvals("ALL"),
        api.config(),
      ]);

    if (ordersResult.status === "fulfilled") setOrders(ordersResult.value);
    if (sessionsResult.status === "fulfilled") setSessions(sessionsResult.value);
    if (approvalsResult.status === "fulfilled") setApprovals(approvalsResult.value);
    if (configResult.status === "fulfilled") setConfig(configResult.value);

    const failures = [ordersResult, sessionsResult, approvalsResult, configResult]
      .filter(
        (result): result is PromiseRejectedResult => result.status === "rejected",
      )
      .map((result) => messageOf(result.reason));
    setDataError(failures.length ? failures[0] : null);
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    setTenantKey(apiKey);
    void refresh(true);
    const handle = window.setInterval(() => void refresh(false), 4000);
    return () => window.clearInterval(handle);
  }, [apiKey, refresh]);

  useEffect(() => {
    if (!toast) return;
    const handle = window.setTimeout(() => setToast(null), 5500);
    return () => window.clearTimeout(handle);
  }, [toast]);

  const handleLoginSuccess = (user: User, token: string) => {
    setCurrentUser(user);
    try {
      window.localStorage.setItem("vanguardcod.user", JSON.stringify(user));
      window.localStorage.setItem("vanguardcod.token", token);
    } catch {
      // Ignored
    }
    setToast({
      kind: "ok",
      text: `Signed in as ${user.name} (${user.role_label}). Welcome to VanguardCOD.`,
    });
  };

  const handleLogout = () => {
    setCurrentUser(null);
    try {
      window.localStorage.removeItem("vanguardcod.user");
      window.localStorage.removeItem("vanguardcod.token");
    } catch {
      // Ignored
    }
    setToast({ kind: "ok", text: "Signed out of VanguardCOD Store Portal." });
  };

  const selectedOrder =
    orders.find((order) => order.id === selectedOrderId) ?? orders[0] ?? null;
  const selectedApproval =
    approvals.find((approval) => approval.id === selectedApprovalId) ??
    approvals.find((approval) => approval.status === "PENDING") ??
    null;
  const pendingApprovals = approvals.filter(
    (approval) => approval.status === "PENDING",
  ).length;

  const handleTrigger = async (order: Order, channel?: string) => {
    setSelectedOrderId(order.id);
    setTriggeringOrderId(order.id);
    try {
      const res = await api.dispatchVerification(order.id, channel);
      const chLabel = res.channel === "WHATSAPP" ? "WhatsApp Conversational Agent" : "Twilio Outbound Voice Call";
      setToast({
        kind: "ok",
        text: `AI verification dispatched via ${chLabel} for Order ${order.external_order_id}.`,
      });
      void refresh(false);
    } catch (error) {
      setToast({ kind: "error", text: messageOf(error) });
    } finally {
      setTriggeringOrderId(null);
    }
  };

  const handleRetry = async (order: Order, channel?: string) => {
    setSelectedOrderId(order.id);
    setTriggeringOrderId(order.id);
    try {
      const res = await api.dispatchVerification(order.id, channel);
      const chLabel = res.channel === "WHATSAPP" ? "WhatsApp Conversational Agent" : "Twilio Outbound Voice Call";
      setToast({
        kind: "ok",
        text: `Retry verification dispatched via ${chLabel} for Order ${order.external_order_id}.`,
      });
      void refresh(false);
    } catch (error) {
      setToast({ kind: "error", text: messageOf(error) });
    } finally {
      setTriggeringOrderId(null);
    }
  };

  const handleDispatchRetries = async () => {
    setDispatchingRetries(true);
    try {
      const res = await api.dispatchRetries(true);
      if (res.dispatched_count > 0) {
        setToast({
          kind: "ok",
          text: `Dispatched ${res.dispatched_count} due retry verification call(s) (${res.orders_retried.join(", ")}).`,
        });
      } else {
        setToast({
          kind: "ok",
          text: "No orders currently pending retry.",
        });
      }
      void refresh(false);
    } catch (error) {
      setToast({ kind: "error", text: messageOf(error) });
    } finally {
      setDispatchingRetries(false);
    }
  };

  const handleIngested = (result: IngestResponse) => {
    setSelectedOrderId(result.order.id);
    setToast({
      kind: "ok",
      text: `Order ${result.order.external_order_id} received. RTO Risk: ${result.order.rto_risk_score}%. Autonomous verification queued.`,
    });
    void refresh(false);
  };

  const openApproval = (approvalId: string) => {
    setSelectedApprovalId(approvalId);
    setApprovalDrawerOpen(true);
  };

  const handleResolve = async (
    approval: Approval,
    approved: boolean,
    note: string,
  ) => {
    setApprovalBusyId(approval.id);
    setApprovalError(null);
    try {
      const response = await api.resolveApproval(approval.id, approved, note);
      setToast({
        kind: "ok",
        text: approved
          ? `Authorized mutation for order ${response.order.external_order_id}.`
          : `Rejected mutation for order ${response.order.external_order_id}. Order returned to queue.`,
      });
      setApprovalDrawerOpen(false);
      void refresh(false);
    } catch (resolveError) {
      setApprovalError(messageOf(resolveError));
    } finally {
      setApprovalBusyId(null);
    }
  };

  // If user is not authenticated, show Modern B2B SaaS Login & Registration Screen
  if (!currentUser) {
    return <LoginView onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <div className="min-h-screen flex flex-col bg-[#F8FAFC] text-slate-900 font-sans">
      {/* Top Modern SaaS Navbar */}
      <SaaSNavbar
        view={view}
        onChangeView={setView}
        currentUser={currentUser}
        onLogout={handleLogout}
        approvalCount={pendingApprovals}
      />

      {/* Main SaaS Workspace */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 md:p-6 space-y-6">
        {/* Error notification banner if any API failed */}
        {dataError ? (
          <div className="bg-red-50 border border-red-200 p-3 rounded-md text-xs text-red-800 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <AlertCircle className="h-4 w-4 text-red-600" />
              Data sync notice: {dataError}
            </span>
            <button
              type="button"
              onClick={() => void refresh(true)}
              className="px-2.5 py-1 bg-white border border-red-200 rounded text-[11px] font-bold text-red-700 hover:bg-red-50 cursor-pointer"
            >
              Retry Sync
            </button>
          </div>
        ) : null}

        {/* 1. OPERATIONS QUEUE VIEW */}
        {view === "operations" ? (
          <div className="space-y-6">
            {/* Quick Hero Banner */}
            <div className="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white rounded-xl p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 text-xs font-semibold text-blue-300 uppercase tracking-wider mb-1">
                  <Sparkles className="h-4 w-4 text-amber-300" />
                  Autonomous COD Protection Engine
                </div>
                <h2 className="text-xl font-bold tracking-tight">
                  Cash-on-Delivery Order Verification Queue
                </h2>
                <p className="text-xs text-slate-300 max-w-2xl mt-1 leading-relaxed">
                  Real-time incoming COD orders from your store. Orders are automatically verified via your configured channels (WhatsApp Conversational Agent or Twilio Voice Calling).
                </p>
              </div>

              <div className="flex items-center gap-3 shrink-0">
                <button
                  type="button"
                  onClick={() => setWebhookOpen(true)}
                  className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition-colors shadow-sm cursor-pointer"
                >
                  Inject Test Webhook Order
                </button>
              </div>
            </div>

            {/* KPI Metric Strip */}
            <KpiStrip orders={orders} sessions={sessions} />

            {/* Order Verification Table */}
            <OrderQueueTable
              orders={orders}
              loading={loading || refreshing}
              selectedOrderId={selectedOrder?.id ?? null}
              activeOrderId={null}
              triggeringOrderId={triggeringOrderId}
              callActive={false}
              onSelect={(order) => setSelectedOrderId(order.id)}
              onTrigger={(order, channel) => void handleTrigger(order, channel)}
              onRetry={(order, channel) => void handleRetry(order, channel)}
              onDispatchRetries={() => void handleDispatchRetries()}
              dispatchingRetries={dispatchingRetries}
              onRefresh={() => void refresh(false)}
              onOpenWebhook={() => setWebhookOpen(true)}
            />
          </div>
        ) : null}

        {/* 2. CALL SESSIONS & TELEMETRY VIEW */}
        {view === "sessions" ? (
          <SessionsView
            sessions={sessions}
            loading={loading || refreshing}
            onRefresh={() => void refresh(false)}
          />
        ) : null}

        {/* 3. MANAGER APPROVAL GATE VIEW */}
        {view === "approvals" ? (
          <ApprovalGate
            approvals={approvals}
            filter={approvalFilter}
            loading={loading || refreshing}
            onFilter={setApprovalFilter}
            onOpen={openApproval}
            onRefresh={() => void refresh(false)}
          />
        ) : null}

        {/* 4. STORE & GOOGLE SHEETS SYNC VIEW */}
        {view === "integrations" ? (
          <StoreAndSheetsView
            orders={orders}
            onOrderCreated={handleIngested}
            onRefresh={() => void refresh(false)}
          />
        ) : null}

        {/* 5. SYSTEM CONFIG VIEW */}
        {view === "config" ? (
          <ConfigView
            config={config}
            apiKey={apiKey}
            onOpenWebhook={() => setWebhookOpen(true)}
          />
        ) : null}
      </main>

      {/* Modal Dialogs */}
      <WebhookSimulatorModal
        open={webhookOpen}
        onClose={() => setWebhookOpen(false)}
        onIngested={handleIngested}
        onCallOrder={(order) => void handleTrigger(order)}
        callActive={false}
      />

      <ApprovalDrawer
        open={approvalDrawerOpen}
        approvals={approvals}
        selectedId={selectedApproval?.id ?? null}
        onSelect={setSelectedApprovalId}
        onClose={() => setApprovalDrawerOpen(false)}
        onResolve={handleResolve}
        busyId={approvalBusyId}
        error={approvalError}
      />

      {/* Toast Notification */}
      {toast ? (
        <div
          role="status"
          className={`fixed bottom-5 left-5 z-[70] max-w-md px-4 py-3 rounded-lg shadow-xl border text-xs font-medium flex items-center gap-2 ${
            toast.kind === "ok"
              ? "bg-slate-900 text-white border-slate-700"
              : "bg-red-900 text-white border-red-700"
          }`}
        >
          {toast.kind === "ok" ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
          ) : (
            <AlertCircle className="h-4 w-4 text-red-400 shrink-0" />
          )}
          <span>{toast.text}</span>
        </div>
      ) : null}
    </div>
  );
}
