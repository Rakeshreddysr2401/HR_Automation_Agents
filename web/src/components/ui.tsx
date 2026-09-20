import { useEffect, useRef, useState, type ReactNode } from "react";
import { IconChevron, IconX } from "./icons";

/**
 * The primitive layer. Every visual decision the app makes more than once
 * lives here, so a change to how (say) a disposition reads is one edit rather
 * than a search across nine panels.
 *
 * Colour is never decorative in this app: a tone means one thing everywhere.
 *   auto   the agent settled it, unambiguously
 *   flag   the agent inferred it and applied it — audit, don't decide
 *   ask    blocked on you
 *   brand  navigation and the agent's own voice
 */
export type Tone = "auto" | "flag" | "ask" | "brand" | "neutral";

const CHIP: Record<Tone, string> = {
  auto: "bg-auto-soft text-auto border-auto/30",
  flag: "bg-flag-soft text-flag border-flag/30",
  ask: "bg-ask-soft text-ask border-ask/30",
  brand: "bg-brand-soft text-brand-ink border-brand/30",
  neutral: "bg-raised text-muted border-line",
};

const INK: Record<Tone, string> = {
  auto: "text-auto",
  flag: "text-flag",
  ask: "text-ask",
  brand: "text-brand",
  neutral: "text-ink",
};

export function Badge({
  tone = "neutral",
  children,
  title,
}: {
  tone?: Tone;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-[1px] text-[var(--text-xs)] leading-[1.6] font-medium whitespace-nowrap ${CHIP[tone]}`}
    >
      {children}
    </span>
  );
}

/** A coloured dot, for a legend or a status line where a chip is too heavy. */
export function Dot({ tone = "neutral", pulse }: { tone?: Tone; pulse?: boolean }) {
  const bg = { auto: "bg-auto", flag: "bg-flag", ask: "bg-ask", brand: "bg-brand", neutral: "bg-faint" }[tone];
  return <span className={`inline-block size-1.5 shrink-0 rounded-full ${bg} ${pulse ? "a-breathe" : ""}`} />;
}

export function Button({
  children,
  onClick,
  variant = "default",
  disabled,
  title,
  size = "md",
  full,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "default" | "primary" | "ghost" | "danger" | "subtle";
  disabled?: boolean;
  title?: string;
  size?: "sm" | "md";
  full?: boolean;
  type?: "button" | "submit";
}) {
  const variants = {
    default: "bg-surface border-line text-ink hover:bg-raised hover:border-faint/50",
    // The one gradient in the app, reserved for the single primary action on
    // screen. If two things glow, neither reads as the next step.
    primary:
      "border-transparent text-[var(--s-on-brand)] shadow-[var(--shadow-sm)] hover:brightness-110 [background-image:var(--s-grad)]",
    subtle: "bg-brand-soft border-brand/25 text-brand-ink hover:border-brand/50",
    ghost: "bg-transparent border-transparent text-muted hover:bg-raised hover:text-ink",
    danger: "bg-surface border-ask/40 text-ask hover:bg-ask-soft hover:border-ask/70",
  }[variant];

  return (
    <button
      type={type}
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-md)] border font-medium
        transition-[background-color,border-color,color,filter] duration-[var(--dur-fast)]
        ${size === "sm" ? "px-2.5 py-1 text-[var(--text-sm)]" : "px-3 py-1.5 text-[var(--text-base)]"}
        ${full ? "w-full" : ""} ${variants}
        disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:brightness-100`}
    >
      {children}
    </button>
  );
}

export function IconButton({
  children,
  onClick,
  title,
  active,
}: {
  children: ReactNode;
  onClick?: () => void;
  title: string;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      aria-pressed={active}
      onClick={onClick}
      className={`inline-flex size-7 items-center justify-center rounded-[var(--radius-md)] border text-[14px]
        transition-colors duration-[var(--dur-fast)]
        ${active
          ? "border-brand/40 bg-brand-soft text-brand-ink"
          : "border-transparent text-muted hover:bg-raised hover:text-ink"}`}
    >
      {children}
    </button>
  );
}

/** A segmented control. Used for the theme, density and audit-actor pickers. */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { id: T; label: ReactNode; title?: string }[];
  onChange: (id: T) => void;
  label?: string;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="inline-flex gap-[2px] rounded-[var(--radius-md)] border border-line bg-sunken p-[2px]"
    >
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          title={option.title}
          aria-pressed={value === option.id}
          onClick={() => onChange(option.id)}
          className={`inline-flex items-center gap-1 rounded-[calc(var(--radius-md)-3px)] px-2 py-[3px]
            text-[var(--text-sm)] font-medium transition-colors duration-[var(--dur-fast)]
            ${value === option.id
              ? "bg-surface text-brand-ink shadow-[var(--shadow-sm)]"
              : "text-muted hover:text-ink"}`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Stat({
  label,
  value,
  tone = "neutral",
  hint,
  onClick,
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
  hint?: string;
  onClick?: () => void;
}) {
  const body = (
    <>
      <div className={`tnum text-[19px] leading-none font-semibold ${INK[tone]}`}>{value}</div>
      <div className="mt-1 truncate text-[var(--text-xs)] text-faint">{label}</div>
    </>
  );
  if (!onClick) {
    return (
      <div className="min-w-0" title={hint}>
        {body}
      </div>
    );
  }
  return (
    <button
      type="button"
      title={hint}
      onClick={onClick}
      className="min-w-0 rounded-[var(--radius-md)] px-1.5 py-0.5 text-left transition-colors hover:bg-raised"
    >
      {body}
    </button>
  );
}

export function Panel({
  title,
  subtitle,
  icon,
  right,
  children,
  flush,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  /** Skip the body padding — for tables and lists that manage their own. */
  flush?: boolean;
}) {
  return (
    <section className="overflow-hidden rounded-[var(--radius-lg)] border border-line bg-surface shadow-[var(--shadow-sm)]">
      {title && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-[var(--panel-pad)] py-2.5">
          <div className="flex min-w-0 items-center gap-2">
            {icon && <span className="shrink-0 text-[15px] text-faint">{icon}</span>}
            <div className="min-w-0">
              <h2 className="truncate text-[var(--text-base)] font-semibold">{title}</h2>
              {subtitle && (
                <p className="truncate text-[var(--text-xs)] text-faint">{subtitle}</p>
              )}
            </div>
          </div>
          {right && <div className="flex shrink-0 items-center gap-2">{right}</div>}
        </header>
      )}
      <div className={flush ? "" : "p-[var(--panel-pad)]"}>{children}</div>
    </section>
  );
}

export function Empty({ icon, children }: { icon?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-12 text-center text-[var(--text-base)] text-faint">
      {icon && <span className="text-[24px] opacity-50">{icon}</span>}
      <p className="max-w-md leading-relaxed">{children}</p>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="mb-0.5 text-[var(--text-xs)] tracking-wide text-faint uppercase">{label}</div>
      <div className="truncate text-[var(--text-base)]">{children}</div>
    </div>
  );
}

export function Input({
  value,
  onChange,
  placeholder,
  icon,
  width = "w-40",
  onKeyDown,
  autoFocus,
  ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  icon?: ReactNode;
  width?: string;
  onKeyDown?: (event: React.KeyboardEvent) => void;
  autoFocus?: boolean;
  ariaLabel?: string;
}) {
  return (
    <div className={`relative ${width}`}>
      {icon && (
        <span className="pointer-events-none absolute top-1/2 left-2 -translate-y-1/2 text-[12px] text-faint">
          {icon}
        </span>
      )}
      <input
        value={value}
        aria-label={ariaLabel ?? placeholder}
        autoFocus={autoFocus}
        onKeyDown={onKeyDown}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className={`w-full rounded-[var(--radius-md)] border border-line bg-sunken py-1
          text-[var(--text-sm)] outline-none transition-colors placeholder:text-faint
          focus:border-brand ${icon ? "pl-7 pr-2" : "px-2"}`}
      />
    </div>
  );
}

/** Redacted sample values from a column profile. */
export function Samples({ values, limit = 6 }: { values: string[]; limit?: number }) {
  if (!values?.length) return <span className="text-faint">no values</span>;
  const shown = values.slice(0, limit);
  return (
    <div className="flex flex-wrap items-center gap-1">
      {shown.map((value, index) => (
        <code
          key={index}
          className="mono rounded-[var(--radius-sm)] border border-line bg-raised px-1.5 py-0.5 text-[var(--text-xs)]"
        >
          {value === "" || value == null ? "(empty)" : value}
        </code>
      ))}
      {values.length > limit && (
        <span className="text-[var(--text-xs)] text-faint">+{values.length - limit}</span>
      )}
    </div>
  );
}

/**
 * A score bar. Tone follows the number, because the same bar is used for
 * "confidence" in three places and a consultant should not have to remember
 * which direction is good.
 */
export function Meter({
  value,
  width = "w-16",
  tone,
  showValue,
}: {
  value: number;
  width?: string;
  tone?: Tone;
  showValue?: boolean;
}) {
  const pct = Math.max(0, Math.min(100, value * 100));
  const auto = value >= 0.82 ? "auto" : value >= 0.5 ? "flag" : "ask";
  const bg = { auto: "bg-auto", flag: "bg-flag", ask: "bg-ask", brand: "bg-brand", neutral: "bg-faint" }[
    tone ?? (auto as Tone)
  ];
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`h-1.5 overflow-hidden rounded-full bg-line ${width}`}>
        <span
          className={`block h-full rounded-full transition-[width] duration-500 ${bg}`}
          style={{ width: `${Math.max(2, pct)}%` }}
        />
      </span>
      {showValue && (
        <span className="mono tnum text-[var(--text-xs)] text-muted">{value.toFixed(2)}</span>
      )}
    </span>
  );
}

export function Spinner({ size = 14 }: { size?: number }) {
  return (
    <span
      className="a-spin inline-block shrink-0 rounded-full border-2 border-line border-t-brand"
      style={{ width: size, height: size }}
      aria-label="working"
    />
  );
}

/** A disclosure row. Used for the decision groups and the evidence sections. */
export function Disclosure({
  summary,
  children,
  defaultOpen,
  right,
}: {
  summary: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  right?: ReactNode;
}) {
  const [open, setOpen] = useState(!!defaultOpen);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2.5 px-[var(--panel-pad)] py-[var(--row-y)] text-left transition-colors hover:bg-raised/50"
      >
        <IconChevron
          className={`shrink-0 text-faint transition-transform duration-[var(--dur-fast)] ${open ? "rotate-90" : ""}`}
        />
        <span className="min-w-0 flex-1">{summary}</span>
        {right}
      </button>
      {open && <div className="a-fade border-t border-line-soft bg-sunken/60">{children}</div>}
    </div>
  );
}

/** A centred overlay. Used for the command palette and the shortcut sheet. */
export function Modal({
  open,
  onClose,
  children,
  label,
  align = "center",
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  label: string;
  align?: "center" | "top";
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex justify-center bg-[oklch(0.15_0.02_258/0.5)] px-4 py-[12vh] backdrop-blur-[3px]"
      style={{ alignItems: align === "top" ? "flex-start" : "center" }}
      onClick={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal
        aria-label={label}
        className="a-pop w-full max-w-lg overflow-hidden rounded-[var(--radius-lg)] border border-line bg-surface shadow-[var(--shadow-lg)]"
      >
        {children}
      </div>
    </div>
  );
}

export function ModalHeader({ title, onClose }: { title: ReactNode; onClose: () => void }) {
  return (
    <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
      <h2 className="text-[var(--text-base)] font-semibold">{title}</h2>
      <IconButton title="Close" onClick={onClose}>
        <IconX />
      </IconButton>
    </header>
  );
}

/** before → after, the shape the audit trail and the dry-run diff both need. */
export function Delta({ before, after }: { before?: unknown; after?: unknown }) {
  const from = before == null || before === "" ? null : String(before);
  const to = after == null || after === "" ? null : String(after);
  return (
    <span className="inline-flex flex-wrap items-baseline gap-1.5">
      {from && (
        <span className="mono text-[var(--text-xs)] text-faint line-through decoration-ask/50">
          {from}
        </span>
      )}
      {from && to && <span className="text-[10px] text-faint">→</span>}
      {to && <span className="mono text-[var(--text-xs)] font-medium">{to}</span>}
      {!from && !to && <span className="text-faint">—</span>}
    </span>
  );
}
