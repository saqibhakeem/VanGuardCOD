export function formatMoney(value: number): string {
  return `PKR ${Math.round(value).toLocaleString("en-US")}`;
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${Math.round(value)} ms`;
}

export function formatDuration(startedAt: number, now: number): string {
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

export function formatClock(value: number | string): string {
  const date = typeof value === "number" ? new Date(value) : new Date(value);
  return date.toLocaleTimeString([], { hour12: false });
}

export function formatDateTime(value: string | number): string {
  const date = typeof value === "number" ? new Date(value) : new Date(value);
  return date.toLocaleString([], {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function shortId(value: string | null | undefined): string {
  if (!value) return "-";
  return value.slice(0, 8);
}

export function maskUrl(value: string | null | undefined): string {
  if (!value) return "-";
  return value.replace(/api_key=[^&]+/, "api_key=***");
}

export function humanize(value: string): string {
  return value
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export type Tone = "verified" | "warning" | "critical" | "neutral" | "accent";

export function riskTone(score: number): Tone {
  if (score > 75) return "critical";
  if (score >= 50) return "warning";
  return "verified";
}

export function latencyTone(totalMs: number): Tone {
  if (totalMs <= 0) return "neutral";
  if (totalMs <= 500) return "verified";
  if (totalMs <= 800) return "warning";
  return "critical";
}

export function statusTone(status: string): Tone {
  switch (status) {
    case "VERIFIED":
    case "SUCCESS":
    case "COMPLETED":
      return "verified";
    case "CALLING":
    case "ACTIVE":
      return "accent";
    case "PENDING_CALL":
    case "RESCHEDULED":
      return "neutral";
    case "NEEDS_APPROVAL":
    case "PAUSED_APPROVAL":
    case "PAUSED_FOR_APPROVAL":
      return "warning";
    case "CANCELLED":
    case "FAILED":
    case "REJECTED":
      return "critical";
    default:
      return "neutral";
  }
}

export const TONE_TEXT: Record<Tone, string> = {
  verified: "text-verified",
  warning: "text-warning",
  critical: "text-critical",
  neutral: "text-ink-2",
  accent: "text-accent",
};

export const TONE_DOT: Record<Tone, string> = {
  verified: "bg-verified",
  warning: "bg-warning",
  critical: "bg-critical",
  neutral: "bg-ink-3",
  accent: "bg-accent",
};

export const TONE_BORDER: Record<Tone, string> = {
  verified: "border-verified/40",
  warning: "border-warning/40",
  critical: "border-critical/40",
  neutral: "border-line",
  accent: "border-accent/40",
};

export const TONE_BG: Record<Tone, string> = {
  verified: "bg-verified/10",
  warning: "bg-warning/10",
  critical: "bg-critical/10",
  neutral: "bg-panel-2",
  accent: "bg-accent/10",
};
