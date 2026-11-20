import {
  Activity,
  FileSpreadsheet,
  LayoutGrid,
  LogOut,
  Settings,
  Shield,
  ShieldCheck,
  Store,
} from "lucide-react";

import type { User, ViewKey } from "../types";

interface Props {
  view: ViewKey;
  onChangeView: (view: ViewKey) => void;
  currentUser: User | null;
  onLogout: () => void;
  approvalCount: number;
}

export function SaaSNavbar({
  view,
  onChangeView,
  currentUser,
  onLogout,
  approvalCount,
}: Props) {
  const tabs: Array<{
    key: ViewKey;
    label: string;
    icon: typeof LayoutGrid;
    badge?: number;
  }> = [
    { key: "operations", label: "Orders Queue", icon: LayoutGrid },
    { key: "sessions", label: "Analytics & Calls", icon: Activity },
    {
      key: "approvals",
      label: "Manager Approvals",
      icon: ShieldCheck,
      badge: approvalCount,
    },
    {
      key: "integrations",
      label: "Integrations & Sheets",
      icon: FileSpreadsheet,
    },
    { key: "config", label: "AI Voice & Settings", icon: Settings },
  ];

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-40 shadow-xs">
      {/* 1. Main SaaS Header Bar */}
      <div className="bg-slate-900 text-white px-5 py-3 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center text-white shadow-sm font-bold">
            <Shield className="h-4 w-4" />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-bold text-sm tracking-tight text-white">
              VanguardCOD
            </span>
            <span className="hidden sm:inline-block px-2 py-0.5 rounded text-[10px] font-medium bg-blue-950 border border-blue-800 text-blue-300">
              COD Voice AI Protection
            </span>
          </div>
        </div>

        {/* Store Profile & User Badge */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-md bg-slate-800 border border-slate-700 text-xs text-slate-300">
            <Store className="h-3.5 w-3.5 text-blue-400" />
            <span className="font-semibold text-slate-200">
              {currentUser?.tenant_name ?? "Karachi Threads & Textiles"}
            </span>
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse ml-1" />
          </div>

          {currentUser ? (
            <div className="flex items-center gap-2 pl-2 border-l border-slate-700">
              <div className="text-right hidden md:block">
                <div className="text-xs font-semibold text-slate-200 leading-tight">
                  {currentUser.name}
                </div>
                <div className="text-[10px] text-blue-300 leading-tight">
                  {currentUser.role_label}
                </div>
              </div>

              <button
                type="button"
                onClick={onLogout}
                className="p-1.5 rounded-md hover:bg-slate-800 text-slate-400 hover:text-red-400 transition-colors cursor-pointer"
                title="Sign out of VanguardCOD"
                aria-label="Sign out"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          ) : null}
        </div>
      </div>

      {/* 2. Secondary Navigation Tabs */}
      <div className="px-5 flex items-center justify-between border-t border-slate-100 bg-white">
        <nav className="flex space-x-1 sm:space-x-2">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const active = view === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => onChangeView(tab.key)}
                className={`flex items-center gap-2 py-3 px-3 text-xs font-medium border-b-2 transition-colors cursor-pointer ${
                  active
                    ? "border-blue-600 text-blue-600 font-semibold"
                    : "border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300"
                }`}
              >
                <Icon className={`h-4 w-4 ${active ? "text-blue-600" : "text-slate-400"}`} />
                <span>{tab.label}</span>
                {tab.badge && tab.badge > 0 ? (
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-amber-500 text-white">
                    {tab.badge}
                  </span>
                ) : null}
              </button>
            );
          })}
        </nav>

        <div className="hidden lg:flex items-center gap-3 text-xs text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            Autonomous Voice Engine Online
          </span>
        </div>
      </div>
    </header>
  );
}
