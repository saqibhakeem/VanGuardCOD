import { LayoutGrid, PhoneCall, ShieldCheck, Webhook } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api, getTenantKey, setTenantKey } from "./api";
import { ApprovalDrawer } from "./components/ApprovalDrawer";
import { ApprovalGate } from "./components/ApprovalGate";
import { ConfigView } from "./components/ConfigView";
import { KpiStrip } from "./components/KpiStrip";
import { LiveCallMonitor } from "./components/LiveCallMonitor";
import { NavRail } from "./components/NavRail";
import { OrderQueueTable } from "./components/OrderQueueTable";
import { SoftphoneDialer } from "./components/SoftphoneDialer";
import { WebhookSimulatorModal } from "./components/WebhookSimulatorModal";
import { useCallSession } from "./hooks/useCallSession";
import type {
  Approval,
  ApprovalStatus,
  CallSessionSummary,
  IngestResponse,
  Order,
  RuntimeConfig,
  ViewKey,
} from "./types";
import { formatClock } from "./lib/format";

type Health = "up" | "down" | "checking";
type ApprovalFilter = ApprovalStatus | "ALL";

const VIEW_META: Record<ViewKey, { title: string; subtitle: string }> = {
  operations: {
    title: "Operations Queue",
    subtitle: "Outbound COD verification and RTO risk control",
  },
  softphone: {
    title: "Softphone Simulator Lab",
    subtitle: "Browser PCM16 voice transport and live agent trace",
  },
  approvals: {
    title: "HITL Approval Gate",
    subtitle: "Human review before any gated mutation executes",
  },
  config: {
    title: "Webhook and Voice Config",
    subtitle: "Runtime, model routing, and wire contracts",
  },
};

const MOBILE_NAV: Array<{ key: ViewKey; label: string; icon: typeof LayoutGrid }> = [
  { key: "operations", label: "Operations queue", icon: LayoutGrid },
  { key: "softphone", label: "Softphone lab", icon: PhoneCall },
  { key: "approvals", label: "Approval gate", icon: ShieldCheck },
  { key: "config", label: "Configuration", icon: Webhook },
];

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export default function App() {
  const [view, setView] = useState<ViewKey>("operations");
  const [apiKey, setApiKey] = useState(getTenantKey());
  const [orders, setOrders] = useState<Order[]>([]);
  const [sessions, setSessions] = useState<CallSessionSummary[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [dataError, setDataError] = useState<string | null>(null);
  const [health, setHealth] = useState<Health>("checking");
  const [lastSync, setLastSync] = useState<number | null>(null);

  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [triggeringOrderId, setTriggeringOrderId] = useState<string | null>(null);
  const [webhookOpen, setWebhookOpen] = useState(false);
  const [approvalFilter, setApprovalFilter] = useState<ApprovalFilter>("PENDING");
  const [approvalDrawerOpen, setApprovalDrawerOpen] = useState(false);
  const [selectedApprovalId, setSelectedApprovalId] = useState<string | null>(null);
  const [approvalBusyId, setApprovalBusyId] = useState<string | null>(null);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const refresh = useCallback(async (spinner = false) => {
    if (spinner) setLoading(true);
    setRefreshing(true);
    const [ordersResult, sessionsResult, approvalsResult, configResult, healthResult] =
      await Promise.allSettled([
        api.orders(),
        api.sessions(),
        api.approvals("ALL"),
        api.config(),
        api.health(),
      ]);

    if (ordersResult.status === "fulfilled") setOrders(ordersResult.value);
    if (sessionsResult.status === "fulfilled") setSessions(sessionsResult.value);
    if (approvalsResult.status === "fulfilled") setApprovals(approvalsResult.value);
    if (configResult.status === "fulfilled") setConfig(configResult.value);
    setHealth(healthResult.status === "fulfilled" ? "up" : "down");

    const failures = [ordersResult, sessionsResult, approvalsResult, configResult]
      .filter(
        (result): result is PromiseRejectedResult => result.status === "rejected",
      )
      .map((result) => messageOf(result.reason));
    setDataError(failures.length ? failures[0] : null);
    setLastSync(Date.now());
    setLoading(false);
    setRefreshing(false);
  }, []);

  const onActivity = useCallback(() => {
    void refresh(false);
  }, [refresh]);

  const call = useCallSession({ onActivity });

  useEffect(() => {
    setTenantKey(apiKey);
    void refresh(true);
    const handle = window.setInterval(() => void refresh(false), 6000);
    return () => window.clearInterval(handle);
  }, [apiKey, refresh]);

  useEffect(() => {
    document.title = `${VIEW_META[view].title} | VanguardCOD`;
  }, [view]);

  useEffect(() => {
    if (!toast) return;
    const handle = window.setTimeout(() => setToast(null), 4500);
    return () => window.clearTimeout(handle);
  }, [toast]);

  useEffect(() => {
    if (call.notice?.startsWith("Operator approval required")) {
      setApprovalFilter("PENDING");
      setApprovalDrawerOpen(true);
      void refresh(false);
    }
  }, [call.notice, refresh]);

  const selectedOrder =
    orders.find((order) => order.id === selectedOrderId) ?? orders[0] ?? null;
  const selectedApproval =
    approvals.find((approval) => approval.id === selectedApprovalId) ??
    approvals.find((approval) => approval.status === "PENDING") ??
    null;
  const pendingApprovals = approvals.filter(
    (approval) => approval.status === "PENDING",
  ).length;
  const callActive =
    call.phase === "connecting" ||
    call.phase === "live" ||
    call.phase === "reconnecting" ||
    call.phase === "ending";
  const activeOrderId = callActive ? (call.call?.order.id ?? null) : null;

  const handleTrigger = async (order: Order) => {
    if (callActive) {
      setToast({ kind: "error", text: "Hang up the current call before triggering another." });
      return;
    }
    setSelectedOrderId(order.id);
    setTriggeringOrderId(order.id);
    try {
      await call.startOutbound(order);
      setToast({
        kind: "ok",
        text: `Outbound verification started for ${order.external_order_id}.`,
      });
    } catch (error) {
      setToast({ kind: "error", text: messageOf(error) });
    } finally {
      setTriggeringOrderId(null);
      void refresh(false);
    }
  };

  const handleIngested = (result: IngestResponse) => {
    setSelectedOrderId(result.order.id);
    setToast({
      kind: "ok",
      text: `${result.order.external_order_id} ingested with RTO score ${result.rto.score}.`,
    });
    void refresh(false);
  };

  const handleResolve = async (approval: Approval, approved: boolean, note: string) => {
    setApprovalBusyId(approval.id);
    setApprovalError(null);
    try {
      await api.resolveApproval(approval.id, approved, note);
      setToast({
        kind: "ok",
        text: `${approval.tool_name} ${approved ? "approved" : "rejected"}.`,
      });
      await refresh(false);
    } catch (error) {
      setApprovalError(messageOf(error));
    } finally {
      setApprovalBusyId(null);
    }
  };

  const openApproval = (approvalId: string) => {
    setSelectedApprovalId(approvalId);
    setApprovalDrawerOpen(true);
    setApprovalError(null);
  };

  const toggleApprovalDrawer = () => {
    if (!approvalDrawerOpen && selectedApproval) {
      setSelectedApprovalId(selectedApproval.id);
    }
    setApprovalDrawerOpen((previous) => !previous);
  };

  return (
    <div className="flex h-screen overflow-hidden bg-canvas text-ink">
      <NavRail
        view={view}
        onChange={setView}
        apiKey={apiKey}
        onApiKeyChange={setApiKey}
        approvalCount={pendingApprovals}
        health={health}
        tenantName={config?.tenant.name ?? "Loading tenant"}
        mockMode={config?.mock_mode ?? true}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-line bg-panel px-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="truncate text-[15px] font-semibold tracking-[-0.01em]">
                {VIEW_META[view].title}
              </h1>
              <span className="hidden border border-line px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3 sm:inline">
                {config?.environment ?? "development"}
              </span>
            </div>
            <div className="truncate font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
              {VIEW_META[view].subtitle}
            </div>
          </div>

          <div className="flex items-center gap-1 md:hidden">
            {MOBILE_NAV.map((item) => {
              const Icon = item.icon;
              const active = view === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setView(item.key)}
                  aria-label={item.label}
                  aria-current={active ? "page" : undefined}
                  className={`relative grid h-8 w-8 place-items-center border ${
                    active
                      ? "border-line bg-panel-2 text-accent"
                      : "border-transparent text-ink-3 hover:text-ink"
                  }`}
                >
                  <Icon className="h-4 w-4" aria-hidden />
                  {item.key === "approvals" && pendingApprovals > 0 ? (
                    <span className="absolute -right-1 -top-1 h-1.5 w-1.5 rounded-full bg-warning" />
                  ) : null}
                </button>
              );
            })}
          </div>

          <div className="hidden items-center gap-3 sm:flex">
            <button
              type="button"
              onClick={toggleApprovalDrawer}
              className="flex items-center gap-1.5 border border-line bg-panel-2 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-2 hover:text-ink"
            >
              <ShieldCheck className="h-3 w-3 text-warning" aria-hidden />
              approvals
              <span className="text-warning">{pendingApprovals}</span>
            </button>
            <div className="hidden items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3 lg:flex">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  health === "up"
                    ? "bg-verified"
                    : health === "checking"
                      ? "bg-warning animate-pulse"
                      : "bg-critical"
                }`}
              />
              {health === "up" ? "API online" : health === "checking" ? "API check" : "API offline"}
            </div>
            <div className="hidden font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3 xl:block">
              sync {lastSync ? formatClock(lastSync) : "-"}
            </div>
            <div className="font-mono text-[9px] uppercase tracking-[0.08em] text-ink-2">
              {formatClock(Date.now())}
            </div>
          </div>
        </header>

        <div className="flex min-h-0 flex-1">
          <main className="min-w-0 flex-1 overflow-y-auto">
            <div className="flex flex-col gap-3 p-4">
              {dataError ? (
                <div className="flex flex-wrap items-center justify-between gap-2 border border-critical/40 bg-critical/10 px-3 py-2 text-[11px] text-critical">
                  <span>Data refresh failed: {dataError}</span>
                  <button
                    type="button"
                    onClick={() => void refresh(true)}
                    className="border border-critical/40 px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.08em] hover:bg-critical/20"
                  >
                    Retry
                  </button>
                </div>
              ) : null}

              {view === "operations" ? (
                <>
                  <KpiStrip orders={orders} sessions={sessions} />
                  <OrderQueueTable
                    orders={orders}
                    loading={loading || refreshing}
                    selectedOrderId={selectedOrder?.id ?? null}
                    activeOrderId={activeOrderId}
                    triggeringOrderId={triggeringOrderId}
                    callActive={callActive}
                    onSelect={(order) => setSelectedOrderId(order.id)}
                    onTrigger={(order) => void handleTrigger(order)}
                    onRefresh={() => void refresh(false)}
                    onOpenWebhook={() => setWebhookOpen(true)}
                  />
                  {loading && orders.length === 0 ? (
                    <div className="border border-line bg-panel px-4 py-6 text-center font-mono text-[11px] text-ink-3">
                      Loading tenant orders...
                    </div>
                  ) : null}
                </>
              ) : null}

              {view === "softphone" ? (
                <div className="grid gap-3 2xl:grid-cols-[380px_1fr]">
                  <div className="xl:hidden">
                    <div className="border border-line bg-panel">
                      <SoftphoneDialer
                        controller={call}
                        orders={orders}
                        selectedOrder={selectedOrder}
                        onSelectOrder={setSelectedOrderId}
                        onActivity={onActivity}
                      />
                    </div>
                  </div>
                  <div className="flex flex-col gap-3">
                    <div className="border border-line bg-panel">
                      <LiveCallMonitor controller={call} variant="full" />
                    </div>
                    <div className="border border-line bg-panel px-3 py-2.5 text-[11px] leading-5 text-ink-2">
                      <span className="font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
                        Runbook
                      </span>
                      <div className="mt-1">
                        Mode 1: select an order, start an outbound call, and act as the buyer
                        through the microphone or the quick replies. Mode 2: start an inbound
                        rescue as a customer or rider. Interrupt flushes agent audio. Use
                        headphones to avoid echo causing a false barge-in.
                      </div>
                      <a
                        href="/softphone"
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 inline-block font-mono text-[10px] uppercase tracking-[0.08em] text-accent hover:text-ink"
                      >
                        Open standalone softphone
                      </a>
                    </div>
                  </div>
                </div>
              ) : null}

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

              {view === "config" ? (
                <ConfigView
                  config={config}
                  apiKey={apiKey}
                  onOpenWebhook={() => setWebhookOpen(true)}
                />
              ) : null}
            </div>
          </main>

          <aside className="hidden w-[400px] shrink-0 overflow-y-auto border-l border-line bg-panel xl:block">
            <div className="sticky top-0 z-10 border-b border-line bg-panel">
              <SoftphoneDialer
                controller={call}
                orders={orders}
                selectedOrder={selectedOrder}
                onSelectOrder={setSelectedOrderId}
                onActivity={onActivity}
                compact
              />
            </div>
            <LiveCallMonitor controller={call} variant="compact" />
          </aside>
        </div>
      </div>

      <WebhookSimulatorModal
        open={webhookOpen}
        onClose={() => setWebhookOpen(false)}
        onIngested={handleIngested}
        onCallOrder={(order) => void handleTrigger(order)}
        callActive={callActive}
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

      {toast ? (
        <div
          role="status"
          className={`fixed bottom-4 right-4 z-[60] max-w-sm border px-3 py-2 text-[11px] shadow-2xl ${
            toast.kind === "ok"
              ? "border-verified/40 bg-[#0c1a14] text-verified"
              : "border-critical/40 bg-[#1b0d0f] text-critical"
          }`}
        >
          {toast.text}
        </div>
      ) : null}
    </div>
  );
}
