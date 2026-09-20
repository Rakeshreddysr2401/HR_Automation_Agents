import { useEffect } from "react";
import { Header } from "./components/Header";
import { RunPanel } from "./components/RunPanel";
import { QueuePanel } from "./components/QueuePanel";
import { MappingPanel } from "./components/MappingPanel";
import { PlanPanel } from "./components/PlanPanel";
import { DecisionsPanel } from "./components/DecisionsPanel";
import { RecordsPanel } from "./components/RecordsPanel";
import { AuditPanel } from "./components/AuditPanel";
import { PolicyPanel } from "./components/PolicyPanel";
import { CommandPalette } from "./components/CommandPalette";
import { ShortcutHelp } from "./components/ShortcutHelp";
import { Toasts } from "./components/Toasts";
import { useStore } from "./state/store";

const VIEWS = {
  run: RunPanel,
  queue: QueuePanel,
  mapping: MappingPanel,
  plan: PlanPanel,
  records: RecordsPanel,
  decisions: DecisionsPanel,
  audit: AuditPanel,
  policy: PolicyPanel,
} as const;

export default function App() {
  const { tab, loadHealth, loadReference, loadHistory } = useStore();
  const View = VIEWS[tab];

  useEffect(() => {
    void loadHealth();
    void loadReference();
    void loadHistory();
  }, [loadHealth, loadReference, loadHistory]);

  return (
    <div className="relative min-h-full">
      <div className="aurora" aria-hidden />
      <div className="relative z-10 flex min-h-full flex-col">
        <Header />
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-3">
          <View />
        </main>
        <footer className="mx-auto w-full max-w-[1400px] px-4 pb-4 text-[var(--text-xs)] text-faint">
          Records never enter a prompt — the agents see redacted column profiles and decide
          rules; deterministic Python applies them to rows. Press <kbd>?</kbd> for shortcuts.
        </footer>
      </div>
      <CommandPalette />
      <ShortcutHelp />
      <Toasts />
    </div>
  );
}
