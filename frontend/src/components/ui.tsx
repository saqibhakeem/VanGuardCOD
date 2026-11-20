import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "danger" | "outline" | "subtle" | "success";
type Size = "sm" | "md" | "lg";

const BASE =
  "inline-flex items-center justify-center gap-1.5 font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 rounded-sm cursor-pointer";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-blue-600 shadow-sm border border-transparent",
  success: "bg-verified text-white hover:bg-emerald-700 shadow-sm border border-transparent",
  danger: "bg-critical text-white hover:bg-red-700 shadow-sm border border-transparent",
  outline: "border border-line bg-panel text-ink hover:bg-panel-2 shadow-xs",
  ghost: "text-ink-2 hover:bg-panel-3 hover:text-ink border border-transparent",
  subtle: "bg-panel-3 text-ink hover:bg-panel-3/80 border border-transparent",
};

const SIZES: Record<Size, string> = {
  sm: "px-2.5 py-1 text-[11px]",
  md: "px-3.5 py-1.5 text-[12px]",
  lg: "px-4 py-2 text-[13px]",
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
  "w-full border border-line bg-panel px-3 py-1.5 text-[12px] text-ink rounded-sm outline-none placeholder:text-ink-3 focus:border-focus focus:ring-1 focus:ring-focus disabled:opacity-50 disabled:bg-panel-2";

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
      className={`flex items-center justify-between gap-2 text-[11px] font-semibold text-ink-2 uppercase tracking-wider ${className}`}
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
      <span className="text-[11px] font-medium text-ink-2">
        {label}
      </span>
      {children}
      {hint ? <span className="text-[11px] leading-4 text-ink-3">{hint}</span> : null}
    </label>
  );
}

