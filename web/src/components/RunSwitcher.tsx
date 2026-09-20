import { useEffect, useRef, useState } from "react";
import { useStore } from "../state/store";
import { IconButton } from "./ui";
import { IconClock } from "./icons";

/**
 * Previous runs, reopenable read-only.
 *
 * Worth having for one specific reason: a migration is reviewed over hours,
 * not minutes, and the consultant who answered half the queue before lunch
 * needs to find their run again. Without this, the run id in the header is a
 * string you have to have written down.
 */
export function RunSwitcher() {
  const { history, loadHistory, openRun, runId } = useStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) void loadHistory();
  }, [open, loadHistory]);

  useEffect(() => {
    if (!open) return;
    function onDown(event: MouseEvent) {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <IconButton title="Previous runs" active={open} onClick={() => setOpen(!open)}>
        <IconClock />
      </IconButton>

      {open && (
        <div className="a-pop absolute top-9 right-0 z-40 w-80 overflow-hidden rounded-[var(--radius-lg)] border border-line bg-surface shadow-[var(--shadow-lg)]">
          <div className="border-b border-line px-3 py-2 text-[var(--text-xs)] tracking-wide text-faint uppercase">
            Previous runs
          </div>
          {history.length === 0 ? (
            <p className="px-3 py-6 text-center text-[var(--text-sm)] text-faint">
              Nothing yet.
            </p>
          ) : (
            <ul className="max-h-80 overflow-y-auto">
              {history.map((run) => (
                <li key={run.run_id}>
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      void openRun(run.run_id);
                    }}
                    className={`flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-raised
                      ${run.run_id === runId ? "bg-brand-soft" : ""}`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="mono truncate text-[var(--text-sm)]">{run.run_id}</div>
                      <div className="truncate text-[var(--text-xs)] text-faint">
                        {run.files.map((f) => f.split("/").pop()).join(", ")}
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="tnum text-[var(--text-sm)]">
                        {run.summary?.records ?? "—"}
                      </div>
                      <div className="text-[var(--text-xs)] text-faint">{run.status}</div>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
