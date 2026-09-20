import { useEffect, useMemo, useState } from "react";
import { useStore, type Tab } from "../state/store";
import { useTheme } from "../state/themeStore";
import { Modal } from "./ui";
import { IconSearch } from "./icons";

interface Command {
  id: string;
  label: string;
  group: string;
  hint?: string;
  run: () => void;
}

/**
 * ⌘K. Worth the ~120 lines because this app has eight views, four appearance
 * controls and a handful of actions — a consultant who has used it twice should
 * never have to hunt for any of them.
 */
export function CommandPalette() {
  const store = useStore();
  const theme = useTheme();
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);

  const commands = useMemo<Command[]>(() => {
    const go = (id: Tab, label: string): Command => ({
      id: `go-${id}`,
      group: "Go to",
      label,
      run: () => store.setTab(id),
    });
    return [
      go("run", "Run (Upload & Progress)"),
      go("queue", "Review (Questions)"),
      go("mapping", "Column Mapping"),
      go("plan", "Preview (Pre-Flight Data)"),
      go("records", "Records (Employee Status)"),
      go("decisions", "Decisions (Auto-Rules)"),
      go("audit", "Audit Trail"),
      go("policy", "Rules & Policy"),
      {
        id: "start",
        group: "Actions",
        label: "Run sample migration (Demo dataset)",
        hint: "two bundled exports",
        run: () => void store.start([]),
      },
      {
        id: "apply",
        group: "Actions",
        label: `Confirm & apply ${Object.keys(store.draft).length} decision(s)`,
        run: () => void store.submit(),
      },
      {
        id: "refresh",
        group: "Actions",
        label: "Reload records, audit and mapping",
        run: () => void store.refresh(),
      },
      {
        id: "plan-refresh",
        group: "Actions",
        label: "Rebuild the dry run",
        run: () => void store.loadPlan(),
      },
      {
        id: "theme",
        group: "Appearance",
        label: `Theme: ${theme.theme} — switch`,
        run: theme.cycleTheme,
      },
      {
        id: "density",
        group: "Appearance",
        label: `Rows: ${theme.density} — switch`,
        run: theme.toggleDensity,
      },
      ...(["indigo", "cyan", "violet", "emerald"] as const).map((accent) => ({
        id: `accent-${accent}`,
        group: "Appearance",
        label: `Accent: ${accent}`,
        run: () => theme.setAccent(accent),
      })),
      {
        id: "help",
        group: "Help",
        label: "Keyboard shortcuts",
        run: () => store.setHelp(true),
      },
    ];
  }, [store, theme]);

  const matches = useMemo(() => {
    if (!query.trim()) return commands;
    const needle = query.toLowerCase();
    return commands.filter((command) =>
      `${command.group} ${command.label} ${command.hint ?? ""}`.toLowerCase().includes(needle),
    );
  }, [commands, query]);

  /**
   * Open with ⌘K / Ctrl+K from anywhere, and "?" for the shortcut sheet.
   *
   * Reads through `useStore.getState()` rather than closing over the store
   * object, so this listener registers once. Depending on the store value would
   * re-subscribe on every state change — and during a run the activity log
   * changes on every progress line, so that is dozens of listener swaps for a
   * handler that never actually varies.
   */
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const state = useStore.getState();
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        state.setPalette(!state.paletteOpen);
        return;
      }
      const target = event.target as HTMLElement;
      const typing = target?.tagName === "INPUT" || target?.tagName === "TEXTAREA";
      if (event.key === "?" && !typing) {
        event.preventDefault();
        state.setHelp(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    setCursor(0);
  }, [query]);

  function close() {
    store.setPalette(false);
    setQuery("");
  }

  function activate(command?: Command) {
    if (!command) return;
    close();
    command.run();
  }

  let lastGroup = "";

  return (
    <Modal open={store.paletteOpen} onClose={close} label="Command palette" align="top">
      <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
        <IconSearch className="shrink-0 text-faint" />
        <input
          autoFocus
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setCursor((c) => Math.min(c + 1, matches.length - 1));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setCursor((c) => Math.max(c - 1, 0));
            } else if (event.key === "Enter") {
              event.preventDefault();
              activate(matches[cursor]);
            }
          }}
          placeholder="Jump to a view, run something, change the theme…"
          className="w-full bg-transparent text-[var(--text-base)] outline-none placeholder:text-faint"
        />
        <kbd>esc</kbd>
      </div>

      <ul className="max-h-[52vh] overflow-y-auto py-1">
        {matches.length === 0 && (
          <li className="px-3 py-6 text-center text-[var(--text-sm)] text-faint">
            Nothing matches “{query}”.
          </li>
        )}
        {matches.map((command, index) => {
          const newGroup = command.group !== lastGroup;
          lastGroup = command.group;
          return (
            <li key={command.id}>
              {newGroup && (
                <div className="px-3 pt-2 pb-1 text-[var(--text-xs)] tracking-wide text-faint uppercase">
                  {command.group}
                </div>
              )}
              <button
                type="button"
                onMouseEnter={() => setCursor(index)}
                onClick={() => activate(command)}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-[var(--text-base)]
                  transition-colors ${index === cursor ? "bg-brand-soft text-brand-ink" : "hover:bg-raised"}`}
              >
                <span className="flex-1 truncate">{command.label}</span>
                {command.hint && (
                  <span className="shrink-0 text-[var(--text-xs)] text-faint">{command.hint}</span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </Modal>
  );
}
