import { riskTone, TONE_TEXT } from "../lib/format";

interface Props {
  score: number;
}

const FILL_CLASS = {
  verified: "bg-verified",
  warning: "bg-warning",
  critical: "bg-critical",
  neutral: "bg-ink-3",
  accent: "bg-accent",
};

export function RtoRiskBar({ score }: Props) {
  const tone = riskTone(score);
  const filled = Math.max(score > 0 ? 1 : 0, Math.round(score / 10));
  return (
    <div className="flex items-center gap-2">
      <div
        className="flex gap-[2px]"
        role="meter"
        aria-label="RTO risk score"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={score}
      >
        {Array.from({ length: 10 }).map((_, index) => (
          <span
            key={index}
            className={`h-2 w-2 border ${
              index < filled
                ? `${FILL_CLASS[tone]} border-transparent`
                : "border-line bg-panel-2"
            }`}
          />
        ))}
      </div>
      <span className={`font-mono text-[11px] ${TONE_TEXT[tone]}`}>{score}</span>
    </div>
  );
}
