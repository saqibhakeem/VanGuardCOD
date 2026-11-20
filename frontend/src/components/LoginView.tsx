import {
  ArrowRight,
  CheckCircle2,
  Copy,
  Lock,
  Shield,
  Store,
  User,
  Zap,
} from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";

import { api, setTenantKey } from "../api";
import type { RegisterStoreResponse, User as AppUser } from "../types";
import { Button, INPUT_CLASS, SELECT_CLASS } from "./ui";

interface Props {
  onLoginSuccess: (user: AppUser, token: string) => void;
}

type AuthMode = "login" | "register";

const DEMO_ROLES = [
  {
    role: "VERIFICATION_OFFICER",
    username: "operator",
    password: "operator123",
    name: "Farhan Ahmed",
    title: "COD Verification Specialist",
    desc: "Reviews incoming COD orders, triggers voice verification calls, and inspects buyer responses.",
    icon: User,
    badgeColor: "bg-blue-50 text-blue-700 border-blue-200",
  },
  {
    role: "LOGISTICS_MANAGER",
    username: "manager",
    password: "manager123",
    name: "Sarah Mansoor",
    title: "Logistics & Risk Manager",
    desc: "Reviews high-risk orders, resolves buyer price disputes and address reroutes in HITL gate.",
    icon: Shield,
    badgeColor: "bg-amber-50 text-amber-700 border-amber-200",
  },
  {
    role: "SYSTEM_ADMIN",
    username: "admin",
    password: "admin123",
    name: "Tariq Malik",
    title: "Store Owner & Administrator",
    desc: "Manages store API keys, Shopify/WooCommerce webhooks, Google Sheets sync, and AI voice persona.",
    icon: Zap,
    badgeColor: "bg-purple-50 text-purple-700 border-purple-200",
  },
];

export function LoginView({ onLoginSuccess }: Props) {
  const [mode, setMode] = useState<AuthMode>("login");

  // Login form state
  const [username, setUsername] = useState("operator");
  const [password, setPassword] = useState("operator123");

  // Registration form state
  const [storeName, setStoreName] = useState("");
  const [regUsername, setRegUsername] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [contactPhone, setContactPhone] = useState("+923001234567");
  const [defaultLanguage, setDefaultLanguage] = useState("en");
  const [voicePersona, setVoicePersona] = useState("troy");
  const [maxAutoApproveCod, setMaxAutoApproveCod] = useState("25000");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [registeredData, setRegisteredData] = useState<RegisterStoreResponse | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);

  const performLogin = async (userToSubmit: string, passToSubmit: string) => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.login(userToSubmit, passToSubmit);
      onLoginSuccess(res.user, res.token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleLoginSubmit = (e: FormEvent) => {
    e.preventDefault();
    void performLogin(username, password);
  };

  const handleRegisterSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const amount = Number(maxAutoApproveCod);
    if (!storeName.trim() || !regUsername.trim() || !regPassword.trim()) {
      setError("Store name, admin username, and password are required.");
      setBusy(false);
      return;
    }

    try {
      const res = await api.registerStore({
        store_name: storeName.trim(),
        admin_username: regUsername.trim(),
        password: regPassword.trim(),
        default_language: defaultLanguage,
        voice_persona: voicePersona,
        max_auto_approve_cod: Number.isFinite(amount) ? amount : 25000,
        contact_phone: contactPhone.trim() || null,
      });

      setTenantKey(res.api_key);
      setRegisteredData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Store registration failed.");
    } finally {
      setBusy(false);
    }
  };

  const copyApiKey = async () => {
    if (!registeredData) return;
    try {
      await navigator.clipboard.writeText(registeredData.api_key);
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    } catch {
      // Ignored
    }
  };

  return (
    <div className="min-h-screen flex flex-col justify-center items-center bg-[#F4F6F9] px-4 py-8">
      {/* Top Modern SaaS Header */}
      <div className="w-full max-w-4xl mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center text-white font-bold text-lg shadow-sm">
            <Shield className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-900 leading-tight">
              VanguardCOD
            </h1>
            <p className="text-xs text-slate-500">
              Autonomous COD Verification & RTO Protection Platform
            </p>
          </div>
        </div>
        <div className="hidden sm:flex items-center gap-2 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-full">
          <span className="h-2 w-2 rounded-full bg-emerald-600 animate-pulse" />
          Autonomous Voice Pipeline Online
        </div>
      </div>

      <div className="w-full max-w-4xl bg-white border border-slate-200 shadow-md rounded-xl overflow-hidden">
        {/* Toggle Mode Bar */}
        <div className="flex border-b border-slate-200 bg-slate-50">
          <button
            type="button"
            onClick={() => {
              setMode("login");
              setError(null);
            }}
            className={`flex-1 py-3 text-xs font-bold text-center border-b-2 transition-colors cursor-pointer ${
              mode === "login"
                ? "border-blue-600 text-blue-600 bg-white"
                : "border-transparent text-slate-500 hover:text-slate-900"
            }`}
          >
            Sign In to Store Account
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("register");
              setError(null);
            }}
            className={`flex-1 py-3 text-xs font-bold text-center border-b-2 transition-colors cursor-pointer ${
              mode === "register"
                ? "border-blue-600 text-blue-600 bg-white"
                : "border-transparent text-slate-500 hover:text-slate-900"
            }`}
          >
            Register New Store / Brand
          </button>
        </div>

        {/* REGISTRATION SUCCESS MODAL */}
        {registeredData ? (
          <div className="p-8 text-center space-y-4">
            <div className="h-12 w-12 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mx-auto">
              <CheckCircle2 className="h-7 w-7" />
            </div>
            <h2 className="text-xl font-bold text-slate-900">
              Store Successfully Onboarded!
            </h2>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              Your business <strong>{registeredData.tenant.name}</strong> is now configured for automated Voice AI order verification.
            </p>

            <div className="max-w-md mx-auto text-left bg-slate-50 p-4 rounded-lg border border-slate-200 space-y-3">
              <div>
                <label className="text-[11px] font-semibold text-slate-500 uppercase block mb-1">
                  Your Store API Key (Store this securely)
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value={registeredData.api_key}
                    className="flex-1 bg-white border border-slate-300 rounded px-2.5 py-1 text-xs font-mono text-slate-900"
                  />
                  <Button size="sm" variant="outline" onClick={copyApiKey}>
                    <Copy className="h-3.5 w-3.5" />
                    {copiedKey ? "Copied" : "Copy"}
                  </Button>
                </div>
              </div>

              <div>
                <label className="text-[11px] font-semibold text-slate-500 uppercase block mb-1">
                  Shopify / WooCommerce Webhook URL
                </label>
                <input
                  type="text"
                  readOnly
                  value={registeredData.webhook_url}
                  className="w-full bg-white border border-slate-300 rounded px-2.5 py-1 text-xs font-mono text-slate-600"
                />
              </div>
            </div>

            <Button
              variant="primary"
              size="lg"
              className="px-8 font-bold"
              onClick={() => onLoginSuccess(registeredData.user, registeredData.token)}
            >
              Open Store Dashboard
              <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        ) : mode === "login" ? (
          /* LOGIN MODE */
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-0">
            {/* Left Side: Modern SaaS Login Form */}
            <div className="lg:col-span-5 p-6 lg:p-8 flex flex-col justify-between border-b lg:border-b-0 lg:border-r border-slate-200">
              <div>
                <div className="flex items-center gap-2 text-xs font-semibold text-blue-600 uppercase tracking-wider mb-2">
                  <Lock className="h-3.5 w-3.5" />
                  Store Authentication
                </div>
                <h2 className="text-xl font-bold text-slate-800">Sign in to Store</h2>
                <p className="text-xs text-slate-500 mt-1">
                  Enter your credentials or choose a pre-configured demo account on the right.
                </p>

                {error ? (
                  <div className="mt-4 p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-xs">
                    {error}
                  </div>
                ) : null}

                <form onSubmit={handleLoginSubmit} className="mt-6 space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      Username or Email
                    </label>
                    <input
                      type="text"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      className={INPUT_CLASS}
                      placeholder="e.g. operator, manager, admin"
                      required
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      Password
                    </label>
                    <input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className={INPUT_CLASS}
                      required
                    />
                  </div>

                  <Button
                    type="submit"
                    variant="primary"
                    disabled={busy}
                    className="w-full py-2 font-semibold flex items-center justify-center gap-2 mt-2 cursor-pointer"
                  >
                    {busy ? "Authenticating..." : "Sign In to VanguardCOD Dashboard"}
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </form>
              </div>

              <div className="mt-6 pt-4 border-t border-slate-100 text-[11px] text-slate-400">
                VanguardCOD Cloud &bull; Multi-Tenant Isolated &bull; Powered by Groq Voice AI
              </div>
            </div>

            {/* Right Side: Role Selector */}
            <div className="lg:col-span-7 p-6 lg:p-8 bg-slate-50/70 flex flex-col justify-between">
              <div>
                <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-3">
                  Pre-Configured Demo Roles
                </h3>
                <p className="text-xs text-slate-600 mb-4">
                  Click any role below to test immediate sign-in:
                </p>

                <div className="space-y-3">
                  {DEMO_ROLES.map((item) => {
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.role}
                        type="button"
                        onClick={() => {
                          setUsername(item.username);
                          setPassword(item.password);
                          void performLogin(item.username, item.password);
                        }}
                        disabled={busy}
                        className="w-full text-left p-3.5 bg-white border border-slate-200 hover:border-[#0070F2] hover:shadow-sm rounded-sm transition-all group flex items-start justify-between gap-3 cursor-pointer"
                      >
                        <div className="flex items-start gap-3">
                          <div className="p-2 rounded-sm bg-slate-100 group-hover:bg-blue-50 text-slate-600 group-hover:text-[#0070F2] transition-colors mt-0.5">
                            <Icon className="h-4 w-4" />
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-bold text-slate-800">
                                {item.name}
                              </span>
                              <span
                                className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${item.badgeColor}`}
                              >
                                {item.title}
                              </span>
                            </div>
                            <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">
                              {item.desc}
                            </p>
                          </div>
                        </div>
                        <ArrowRight className="h-4 w-4 text-slate-300 group-hover:text-[#0070F2] group-hover:translate-x-0.5 transition-all shrink-0 mt-2" />
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        ) : (
          /* REGISTRATION MODE */
          <div className="p-6 lg:p-8">
            <div className="max-w-2xl mx-auto">
              <div className="flex items-center gap-2 text-xs font-semibold text-[#0070F2] uppercase tracking-wider mb-2">
                <Store className="h-4 w-4" />
                New Merchant Onboarding
              </div>
              <h2 className="text-xl font-bold text-slate-900">
                Register Your Business / Online Store
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                Connect your e-commerce store (Shopify, WooCommerce, or custom order form) to autonomous voice verification.
              </p>

              {error ? (
                <div className="mt-4 p-3 rounded-sm bg-red-50 border border-red-200 text-red-700 text-xs">
                  {error}
                </div>
              ) : null}

              <form onSubmit={handleRegisterSubmit} className="mt-6 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      Business / Store Name *
                    </label>
                    <input
                      type="text"
                      value={storeName}
                      onChange={(e) => setStoreName(e.target.value)}
                      placeholder="e.g. Al-Karam Studio, Gul Ahmed"
                      className={INPUT_CLASS}
                      required
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      Contact Phone *
                    </label>
                    <input
                      type="text"
                      value={contactPhone}
                      onChange={(e) => setContactPhone(e.target.value)}
                      placeholder="+923001234567"
                      className={INPUT_CLASS}
                      required
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      Admin Username *
                    </label>
                    <input
                      type="text"
                      value={regUsername}
                      onChange={(e) => setRegUsername(e.target.value)}
                      placeholder="e.g. store_admin"
                      className={INPUT_CLASS}
                      required
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      Password *
                    </label>
                    <input
                      type="password"
                      value={regPassword}
                      onChange={(e) => setRegPassword(e.target.value)}
                      className={INPUT_CLASS}
                      required
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      Verification Language
                    </label>
                    <select
                      value={defaultLanguage}
                      onChange={(e) => setDefaultLanguage(e.target.value)}
                      className={SELECT_CLASS}
                    >
                      <option value="en">English (default)</option>
                      <option value="ur">Urdu (Roman / Urdu)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      AI Voice Persona
                    </label>
                    <select
                      value={voicePersona}
                      onChange={(e) => setVoicePersona(e.target.value)}
                      className={SELECT_CLASS}
                    >
                      <option value="troy">Troy (Professional Male)</option>
                      <option value="hannah">Hannah (Professional Female)</option>
                      <option value="austin">Austin (Friendly Male)</option>
                      <option value="daniel">Daniel (Clear Male)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      Auto-Approve COD Limit (PKR)
                    </label>
                    <input
                      type="number"
                      value={maxAutoApproveCod}
                      onChange={(e) => setMaxAutoApproveCod(e.target.value)}
                      className={INPUT_CLASS}
                    />
                  </div>
                </div>

                <div className="pt-3 flex justify-end">
                  <Button
                    type="submit"
                    variant="primary"
                    disabled={busy}
                    className="px-6 py-2.5 font-bold flex items-center gap-2"
                  >
                    {busy ? "Registering Store..." : "Complete Store Registration"}
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
