import { useStore } from "../state/store";
import { IconCheck, IconAlert, IconSpark, IconX } from "./icons";

/** Transient confirmations. Anything that needs to persist goes in the audit
 *  trail instead — a toast is for "that worked", never for a record of it. */
export function Toasts() {
  const { toasts, dismissToast } = useStore();
  if (!toasts.length) return null;

  return (
    <div
      className="pointer-events-none fixed right-4 bottom-4 z-50 flex flex-col items-end gap-2"
      role="status"
      aria-live="polite"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`a-pop pointer-events-auto flex max-w-sm items-start gap-2 rounded-[var(--radius-lg)] border
            px-3 py-2 text-[var(--text-sm)] shadow-[var(--shadow-lg)]
            ${toast.tone === "auto"
              ? "border-auto/30 bg-auto-soft text-auto"
              : toast.tone === "ask"
                ? "border-ask/30 bg-ask-soft text-ask"
                : "border-brand/30 bg-brand-soft text-brand-ink"}`}
        >
          <span className="mt-0.5 shrink-0">
            {toast.tone === "auto" ? <IconCheck /> : toast.tone === "ask" ? <IconAlert /> : <IconSpark />}
          </span>
          <span className="flex-1">{toast.text}</span>
          <button
            type="button"
            onClick={() => dismissToast(toast.id)}
            aria-label="Dismiss"
            className="shrink-0 opacity-60 hover:opacity-100"
          >
            <IconX />
          </button>
        </div>
      ))}
    </div>
  );
}
