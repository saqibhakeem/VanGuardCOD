import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  Copy,
  Layers,
  Loader2,
  Lock,
  MessageSquare,
  PhoneCall,
  Shield,
  Store,
} from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";

import { api, setTenantKey } from "../api";
import type {
  ChannelChoice,
  OmnichannelStrategy,
  RegisterStoreResponse,
  TestTwilioResponse,
  TestWhatsAppResponse,
  User as AppUser,
  WhatsAppProvider,
} from "../types";
import { Button, INPUT_CLASS, SELECT_CLASS } from "./ui";

interface Props {
  onLoginSuccess: (user: AppUser, token: string) => void;
}

type AuthMode = "login" | "register";

export function LoginView({ onLoginSuccess }: Props) {
  const [mode, setMode] = useState<AuthMode>(() => {
    try {
      return new URLSearchParams(window.location.search).get("mode") === "register" ? "register" : "login";
    } catch {
      return "login";
    }
  });

  // Login form state
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  // Registration form state
  const [storeName, setStoreName] = useState("");
  const [regUsername, setRegUsername] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [defaultLanguage, setDefaultLanguage] = useState("en");
  const [voicePersona, setVoicePersona] = useState("troy");
  const [maxAutoApproveCod, setMaxAutoApproveCod] = useState("25000");

  // SaaS Communication Channels state
  const [channelChoice, setChannelChoice] = useState<ChannelChoice>("BOTH");
  const [omnichannelStrategy, setOmnichannelStrategy] = useState<OmnichannelStrategy>("WHATSAPP_FIRST");

  // Twilio BYOK fields
  const [twilioAccountSid, setTwilioAccountSid] = useState("");
  const [twilioAuthToken, setTwilioAuthToken] = useState("");
  const [twilioFromNumber, setTwilioFromNumber] = useState("");
  const [testingTwilio, setTestingTwilio] = useState(false);
  const [twilioTestResult, setTwilioTestResult] = useState<TestTwilioResponse | null>(null);

  // WhatsApp BYOK fields
  const [whatsappProvider, setWhatsappProvider] = useState<WhatsAppProvider>("META");
  const [whatsappPhoneNumberId, setWhatsappPhoneNumberId] = useState("");
  const [whatsappAccessToken, setWhatsappAccessToken] = useState("");
  const [whatsappWabaId, setWhatsappWabaId] = useState("");
  const [testingWhatsApp, setTestingWhatsApp] = useState(false);
  const [whatsAppTestResult, setWhatsAppTestResult] = useState<TestWhatsAppResponse | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [registeredData, setRegisteredData] = useState<RegisterStoreResponse | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);

  const handleTestTwilio = async () => {
    setTestingTwilio(true);
    setTwilioTestResult(null);
    try {
      const res = await api.testTwilio({
        account_sid: twilioAccountSid.trim() || "mock_sid",
        auth_token: twilioAuthToken.trim() || "mock_token",
        from_number: twilioFromNumber.trim() || "+15551234567",
      });
      setTwilioTestResult(res);
    } catch (err) {
      setTwilioTestResult({
        valid: false,
        message: err instanceof Error ? err.message : "Failed to verify Twilio credentials",
      });
    } finally {
      setTestingTwilio(false);
    }
  };

  const handleTestWhatsApp = async () => {
    setTestingWhatsApp(true);
    setWhatsAppTestResult(null);
    try {
      const res = await api.testWhatsApp({
        provider: whatsappProvider,
        phone_number_id: whatsappPhoneNumberId.trim() || "mock_phone_id",
        access_token: whatsappAccessToken.trim() || "mock_access_token",
        waba_id: whatsappWabaId.trim() || null,
        twilio_account_sid: twilioAccountSid.trim() || null,
        twilio_auth_token: twilioAuthToken.trim() || null,
        twilio_from_number: twilioFromNumber.trim() || null,
      });
      setWhatsAppTestResult(res);
    } catch (err) {
      setWhatsAppTestResult({
        valid: false,
        message: err instanceof Error ? err.message : "Failed to verify WhatsApp credentials",
      });
    } finally {
      setTestingWhatsApp(false);
    }
  };

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
        channel_choice: channelChoice,
        twilio_account_sid: twilioAccountSid.trim() || null,
        twilio_auth_token: twilioAuthToken.trim() || null,
        twilio_from_number: twilioFromNumber.trim() || null,
        whatsapp_provider: whatsappProvider,
        whatsapp_phone_number_id: whatsappPhoneNumberId.trim() || null,
        whatsapp_access_token: whatsappAccessToken.trim() || null,
        whatsapp_waba_id: whatsappWabaId.trim() || null,
        omnichannel_strategy: omnichannelStrategy,
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
          Autonomous Verification Engine Online
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
              Your business <strong>{registeredData.tenant.name}</strong> is now configured for automated Voice and WhatsApp AI order verification.
            </p>

            <div className="flex items-center justify-center gap-2 my-2">
              <span className="text-xs font-semibold text-slate-600">Active Channels:</span>
              {(registeredData.tenant.channel_choice === "WHATSAPP" || registeredData.tenant.channel_choice === "BOTH") ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                  <MessageSquare className="h-3.5 w-3.5" /> WhatsApp Chat Agent
                </span>
              ) : null}
              {(registeredData.tenant.channel_choice === "TWILIO" || registeredData.tenant.channel_choice === "BOTH") ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 border border-blue-200">
                  <PhoneCall className="h-3.5 w-3.5" /> Twilio Voice Calls
                </span>
              ) : null}
            </div>

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
          /* LOGIN MODE - CLEAN SAAS AUTHENTICATION */
          <div className="p-8 max-w-lg mx-auto w-full">
            <div className="flex items-center gap-2 text-xs font-semibold text-blue-600 uppercase tracking-wider mb-2">
              <Lock className="h-4 w-4" />
              Store Authentication
            </div>
            <h2 className="text-xl font-bold text-slate-900">Sign in to Store Account</h2>
            <p className="text-xs text-slate-500 mt-1">
              Enter your administrator credentials to access your VanguardCOD merchant portal.
            </p>

            {error ? (
              <div className="mt-4 p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-xs">
                {error}
              </div>
            ) : null}

            <form onSubmit={handleLoginSubmit} className="mt-6 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Administrator Username
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className={INPUT_CLASS}
                  placeholder="e.g. store_admin"
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
                  placeholder="Enter your password"
                  required
                />
              </div>

              <Button
                type="submit"
                variant="primary"
                disabled={busy}
                className="w-full py-2.5 font-bold flex items-center justify-center gap-2 mt-2 cursor-pointer"
              >
                {busy ? "Authenticating..." : "Sign In to Dashboard"}
                <ArrowRight className="h-4 w-4" />
              </Button>
            </form>

            <div className="mt-6 pt-4 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
              <span>New merchant?</span>
              <button
                type="button"
                onClick={() => {
                  setMode("register");
                  setError(null);
                }}
                className="font-bold text-blue-600 hover:text-blue-700 cursor-pointer"
              >
                Register your business &rarr;
              </button>
            </div>

            <div className="mt-4 text-center text-[11px] text-slate-400">
              VanguardCOD Cloud &bull; Multi-Tenant Isolated &bull; Powered by Voice & WhatsApp AI
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

                {/* Communication Channel Selection (WhatsApp / Twilio / Both) */}
                <div className="pt-4 border-t border-slate-200">
                  <div className="flex items-center gap-2 text-xs font-bold text-slate-800 uppercase tracking-wider mb-1">
                    <Layers className="h-4 w-4 text-blue-600" />
                    Choose Verification Channel(s)
                  </div>
                  <p className="text-xs text-slate-500 mb-3">
                    Select how VanguardCOD should verify orders with your customers. You can adjust keys anytime in settings.
                  </p>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {/* WhatsApp Option */}
                    <div
                      onClick={() => setChannelChoice("WHATSAPP")}
                      className={`p-3.5 rounded-lg border cursor-pointer transition-all ${
                        channelChoice === "WHATSAPP"
                          ? "border-emerald-500 bg-emerald-50/50 shadow-xs ring-1 ring-emerald-500"
                          : "border-slate-200 bg-white hover:border-slate-300"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className={`p-2 rounded-md ${channelChoice === "WHATSAPP" ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
                          <MessageSquare className="h-4 w-4" />
                        </div>
                        {channelChoice === "WHATSAPP" ? (
                          <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                        ) : null}
                      </div>
                      <div className="text-xs font-bold text-slate-900">WhatsApp Chat Agent</div>
                      <p className="text-[11px] text-slate-500 mt-1 leading-snug">
                        Multi-turn conversational chat agent confirms orders, negotiates delivery slots, and records landmarks on WhatsApp.
                      </p>
                    </div>

                    {/* Twilio Voice Option */}
                    <div
                      onClick={() => setChannelChoice("TWILIO")}
                      className={`p-3.5 rounded-lg border cursor-pointer transition-all ${
                        channelChoice === "TWILIO"
                          ? "border-blue-500 bg-blue-50/50 shadow-xs ring-1 ring-blue-500"
                          : "border-slate-200 bg-white hover:border-slate-300"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className={`p-2 rounded-md ${channelChoice === "TWILIO" ? "bg-blue-100 text-blue-700" : "bg-slate-100 text-slate-600"}`}>
                          <PhoneCall className="h-4 w-4" />
                        </div>
                        {channelChoice === "TWILIO" ? (
                          <CheckCircle2 className="h-4 w-4 text-blue-600" />
                        ) : null}
                      </div>
                      <div className="text-xs font-bold text-slate-900">Twilio Phone Call</div>
                      <p className="text-[11px] text-slate-500 mt-1 leading-snug">
                        Autonomous AI voice agent places real outbound calls via Twilio to verify customer orders with natural speech.
                      </p>
                    </div>

                    {/* Both Option */}
                    <div
                      onClick={() => setChannelChoice("BOTH")}
                      className={`p-3.5 rounded-lg border cursor-pointer transition-all relative ${
                        channelChoice === "BOTH"
                          ? "border-indigo-500 bg-indigo-50/50 shadow-xs ring-1 ring-indigo-500"
                          : "border-slate-200 bg-white hover:border-slate-300"
                      }`}
                    >
                      <span className="absolute -top-2 right-2 px-1.5 py-0.5 text-[9px] font-bold uppercase rounded bg-indigo-600 text-white shadow-xs">
                        Recommended
                      </span>
                      <div className="flex items-center justify-between mb-2">
                        <div className={`p-2 rounded-md ${channelChoice === "BOTH" ? "bg-indigo-100 text-indigo-700" : "bg-slate-100 text-slate-600"}`}>
                          <Layers className="h-4 w-4" />
                        </div>
                        {channelChoice === "BOTH" ? (
                          <CheckCircle2 className="h-4 w-4 text-indigo-600" />
                        ) : null}
                      </div>
                      <div className="text-xs font-bold text-slate-900">Both (Omnichannel)</div>
                      <p className="text-[11px] text-slate-500 mt-1 leading-snug">
                        Smart omnichannel routing: verify via WhatsApp chat agent or natural phone call with automated fallback.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Omnichannel Fallback Strategy (When BOTH selected) */}
                {channelChoice === "BOTH" ? (
                  <div className="p-3 bg-indigo-50/50 border border-indigo-200 rounded-lg">
                    <label className="block text-xs font-semibold text-indigo-900 mb-1">
                      Omnichannel Routing Strategy
                    </label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1">
                      <label className="flex items-start gap-2 p-2 bg-white rounded border border-indigo-100 cursor-pointer">
                        <input
                          type="radio"
                          name="omnichannelStrategy"
                          value="WHATSAPP_FIRST"
                          checked={omnichannelStrategy === "WHATSAPP_FIRST"}
                          onChange={() => setOmnichannelStrategy("WHATSAPP_FIRST")}
                          className="text-indigo-600 mt-0.5"
                        />
                        <div className="text-xs">
                          <div className="font-semibold text-slate-800">WhatsApp First (Recommended)</div>
                          <div className="text-[10px] text-slate-500">Send WhatsApp first; dispatch phone call if no reply within 1 hour</div>
                        </div>
                      </label>
                      <label className="flex items-start gap-2 p-2 bg-white rounded border border-indigo-100 cursor-pointer">
                        <input
                          type="radio"
                          name="omnichannelStrategy"
                          value="VOICE_FIRST"
                          checked={omnichannelStrategy === "VOICE_FIRST"}
                          onChange={() => setOmnichannelStrategy("VOICE_FIRST")}
                          className="text-indigo-600 mt-0.5"
                        />
                        <div className="text-xs">
                          <div className="font-semibold text-slate-800">Voice First</div>
                          <div className="text-[10px] text-slate-500">Call phone first; send WhatsApp message if customer does not answer</div>
                        </div>
                      </label>
                    </div>
                  </div>
                ) : null}

                {/* Twilio Voice BYOK Credentials */}
                {(channelChoice === "TWILIO" || channelChoice === "BOTH") ? (
                  <div className="p-4 border border-blue-200 bg-blue-50/30 rounded-lg space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <PhoneCall className="h-4 w-4 text-blue-600" />
                        <span className="text-xs font-bold text-slate-900">Twilio Voice Provider Credentials</span>
                      </div>
                      <span className="text-[10px] text-slate-500 bg-white px-2 py-0.5 rounded border border-slate-200">
                        Leave blank for Mock mode
                      </span>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div>
                        <label className="block text-[11px] font-medium text-slate-700 mb-1">
                          Twilio Account SID
                        </label>
                        <input
                          type="text"
                          value={twilioAccountSid}
                          onChange={(e) => setTwilioAccountSid(e.target.value)}
                          placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxx"
                          className={INPUT_CLASS}
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-medium text-slate-700 mb-1">
                          Twilio Auth Token
                        </label>
                        <input
                          type="password"
                          value={twilioAuthToken}
                          onChange={(e) => setTwilioAuthToken(e.target.value)}
                          placeholder="Auth Token"
                          className={INPUT_CLASS}
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-medium text-slate-700 mb-1">
                          Twilio From Number
                        </label>
                        <input
                          type="text"
                          value={twilioFromNumber}
                          onChange={(e) => setTwilioFromNumber(e.target.value)}
                          placeholder="+1xxxxxxxxxx"
                          className={INPUT_CLASS}
                        />
                      </div>
                    </div>

                    <div className="flex items-center justify-between pt-1">
                      <div className="text-[11px]">
                        {twilioTestResult ? (
                          <span className={`flex items-center gap-1 font-medium ${twilioTestResult.valid ? "text-emerald-700" : "text-red-700"}`}>
                            {twilioTestResult.valid ? <Check className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
                            {twilioTestResult.message}
                          </span>
                        ) : (
                          <span className="text-slate-500">Test live credentials before saving</span>
                        )}
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={handleTestTwilio}
                        disabled={testingTwilio}
                        className="bg-white border-blue-200 text-blue-700 hover:bg-blue-50"
                      >
                        {testingTwilio ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                        {testingTwilio ? "Verifying..." : "Test Twilio Connection"}
                      </Button>
                    </div>
                  </div>
                ) : null}

                {/* WhatsApp BYOK Credentials */}
                {(channelChoice === "WHATSAPP" || channelChoice === "BOTH") ? (
                  <div className="p-4 border border-emerald-200 bg-emerald-50/30 rounded-lg space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <MessageSquare className="h-4 w-4 text-emerald-600" />
                        <span className="text-xs font-bold text-slate-900">WhatsApp Business API Credentials</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <select
                          value={whatsappProvider}
                          onChange={(e) => setWhatsappProvider(e.target.value as WhatsAppProvider)}
                          className={`${SELECT_CLASS} text-xs py-0.5`}
                        >
                          <option value="META">Meta Cloud API (Official)</option>
                          <option value="TWILIO">Twilio WhatsApp</option>
                        </select>
                      </div>
                    </div>

                    {whatsappProvider === "META" ? (
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div>
                          <label className="block text-[11px] font-medium text-slate-700 mb-1">
                            Meta Phone Number ID
                          </label>
                          <input
                            type="text"
                            value={whatsappPhoneNumberId}
                            onChange={(e) => setWhatsappPhoneNumberId(e.target.value)}
                            placeholder="e.g. 10482910482910"
                            className={INPUT_CLASS}
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] font-medium text-slate-700 mb-1">
                            System User Access Token
                          </label>
                          <input
                            type="password"
                            value={whatsappAccessToken}
                            onChange={(e) => setWhatsappAccessToken(e.target.value)}
                            placeholder="EAAxxxxxxxx..."
                            className={INPUT_CLASS}
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] font-medium text-slate-700 mb-1">
                            WABA Account ID
                          </label>
                          <input
                            type="text"
                            value={whatsappWabaId}
                            onChange={(e) => setWhatsappWabaId(e.target.value)}
                            placeholder="Optional WABA ID"
                            className={INPUT_CLASS}
                          />
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-slate-600">
                        Twilio WhatsApp uses your Twilio Account SID, Auth Token, and From Number configured above (e.g. <code>whatsapp:+14155238886</code>).
                      </p>
                    )}

                    <div className="flex items-center justify-between pt-1">
                      <div className="text-[11px]">
                        {whatsAppTestResult ? (
                          <span className={`flex items-center gap-1 font-medium ${whatsAppTestResult.valid ? "text-emerald-700" : "text-red-700"}`}>
                            {whatsAppTestResult.valid ? <Check className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
                            {whatsAppTestResult.message}
                          </span>
                        ) : (
                          <span className="text-slate-500">Test live Meta WhatsApp credentials</span>
                        )}
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={handleTestWhatsApp}
                        disabled={testingWhatsApp}
                        className="bg-white border-emerald-200 text-emerald-700 hover:bg-emerald-50"
                      >
                        {testingWhatsApp ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                        {testingWhatsApp ? "Verifying..." : "Test WhatsApp Connection"}
                      </Button>
                    </div>
                  </div>
                ) : null}

                <div className="pt-3 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => {
                      setMode("login");
                      setError(null);
                    }}
                    className="text-xs font-semibold text-slate-500 hover:text-slate-800 cursor-pointer"
                  >
                    &larr; Already have an account? Sign In
                  </button>
                  <Button
                    type="submit"
                    variant="primary"
                    disabled={busy}
                    className="px-6 py-2.5 font-bold flex items-center gap-2 cursor-pointer"
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
