import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "danger" | "outline" | "subtle";
type Size = "sm" | "md";

const BASE =
  "inline-flex items-center justify-center gap-1.5 border font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40";

const VARIANTS: Record<Variant, string> = {
  primary: "border-focus bg-focus/15 text-ink hover:bg-focus/25",
  ghost:
    "border-transparent text-ink-2 hover:border-line hover:bg-panel-2 hover:text-ink",
  danger: "border-critical/40 bg-critical/10 text-critical hover:bg-critical/20",
  outline:
    "border-line bg-panel-2 text-ink-2 hover:border-ink-3/50 hover:text-ink",
  subtle: "border-transparent bg-panel-2 text-ink-2 hover:text-ink",
};

const SIZES: Record<Size, string> = {
  sm: "px-2 py-1 text-[11px]",
  md: "px-3 py-1.5 text-[12px]",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export function Button({
  variant = "outline",
  size = "md",
  className = "",
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`${BASE} ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...props}
    />
  );
}

export const INPUT_CLASS =
  "w-full border border-line bg-panel-2 px-2.5 py-1.5 text-[12px] text-ink outline-none placeholder:text-ink-3 focus:border-focus disabled:opacity-50";

export const SELECT_CLASS = `${INPUT_CLASS} appearance-none`;

export function SectionLabel({
  children,
  right,
  className = "",
}: {
  children: ReactNode;
  right?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`flex items-center justify-between gap-2 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-2 ${className}`}
    >
      <span>{children}</span>
      {right}
    </div>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
        {label}
      </span>
      {children}
      {hint ? <span className="text-[10px] leading-4 text-ink-3">{hint}</span> : null}
    </label>
  );
}
