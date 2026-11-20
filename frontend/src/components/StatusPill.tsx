import type { Tone } from "../lib/format";
import {
  humanize,
  statusTone,
  TONE_BG,
  TONE_BORDER,
  TONE_DOT,
  TONE_TEXT,
} from "../lib/format";

interface Props {
  status: string;
  label?: string;
  tone?: Tone;
  dot?: boolean;
}

export function StatusPill({ status, label, tone, dot = true }: Props) {
  const resolved = tone ?? statusTone(status);
  return (
    <span
      className={`inline-flex items-center gap-1.5 border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] ${TONE_TEXT[resolved]} ${TONE_BORDER[resolved]} ${TONE_BG[resolved]}`}
    >
      {dot ? <span className={`h-1.5 w-1.5 rounded-full ${TONE_DOT[resolved]}`} /> : null}
      {label ?? humanize(status)}
    </span>
  );
}
