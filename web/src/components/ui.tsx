import type { ReactNode } from "react";

/** Colour is never decorative here: each tone means one thing, everywhere. */
export type Tone = "auto" | "flag" | "ask" | "brand" | "neutral";

const TONES: Record<Tone, string> = {
  auto: "bg-auto-soft text-auto border-auto/25",
  flag: "bg-flag-soft text-flag border-flag/25",
  ask: "bg-ask-soft text-ask border-ask/25",
  brand: "bg-brand-soft text-brand border-brand/25",
  neutral: "bg-raised text-muted border-line",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

export function Button({
  children,
  onClick,
  variant = "default",
  disabled,
  title,
  size = "md",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "default" | "primary" | "ghost" | "danger";
  disabled?: boolean;
  title?: string;
  size?: "sm" | "md";
}) {
  const variants = {
    default: "bg-surface border-line text-ink hover:bg-raised",
    primary: "bg-brand border-brand text-white hover:opacity-90",
    ghost: "bg-transparent border-transparent text-muted hover:bg-raised hover:text-ink",
    danger: "bg-surface border-ask/40 text-ask hover:bg-ask-soft",
  };
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg border font-medium transition
        ${size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-[13px]"}
        ${variants[variant]} disabled:cursor-not-allowed disabled:opacity-40`}
    >
      {children}
    </button>
  );
}

export function Stat({
  label,
  value,
  tone = "neutral",
  hint,
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
  hint?: string;
}) {
  const colour = {
    auto: "text-auto",
    flag: "text-flag",
    ask: "text-ask",
    brand: "text-brand",
    neutral: "text-ink",
  }[tone];
  return (
    <div className="min-w-0" title={hint}>
      <div className={`text-xl font-semibold tabular-nums ${colour}`}>{value}</div>
      <div className="truncate text-[11px] text-faint">{label}</div>
    </div>
  );
}

export function Panel({
  title,
  right,
  children,
  subtitle,
}: {
  title?: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-line bg-surface">
      {title && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <div className="min-w-0">
            <h2 className="text-[13px] font-semibold">{title}</h2>
            {subtitle && <p className="truncate text-[11px] text-faint">{subtitle}</p>}
          </div>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="px-4 py-12 text-center text-[13px] text-faint">{children}</div>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="mb-0.5 text-[10px] tracking-wide text-faint uppercase">{label}</div>
      <div className="truncate text-[13px]">{children}</div>
    </div>
  );
}

export function Samples({ values }: { values: string[] }) {
  if (!values?.length) return <span className="text-faint">no values</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {values.map((value, index) => (
        <code
          key={index}
          className="mono rounded border border-line bg-raised px-1.5 py-0.5 text-[11px]"
        >
          {value || "(empty)"}
        </code>
      ))}
    </div>
  );
}

export function Meter({ value }: { value: number }) {
  return (
    <div className="h-1.5 w-16 overflow-hidden rounded-full bg-line">
      <div
        className="h-full rounded-full bg-brand"
        style={{ width: `${Math.max(2, Math.min(100, value * 100))}%` }}
      />
    </div>
  );
}
