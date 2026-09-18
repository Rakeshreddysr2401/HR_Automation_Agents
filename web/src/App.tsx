import { useEffect } from "react";
import { Header } from "./components/Header";
import { RunPanel } from "./components/RunPanel";
import { QueuePanel } from "./components/QueuePanel";
import { DecisionsPanel } from "./components/DecisionsPanel";
import { RecordsPanel } from "./components/RecordsPanel";
import { AuditPanel } from "./components/AuditPanel";
import { useStore } from "./state/store";

export default function App() {
  const { tab, loadHealth } = useStore();

  useEffect(() => {
    void loadHealth();
  }, [loadHealth]);

  return (
    <div className="min-h-full">
      <Header />
      <main className="mx-auto max-w-7xl px-4 py-4">
        {tab === "run" && <RunPanel />}
        {tab === "queue" && <QueuePanel />}
        {tab === "decisions" && <DecisionsPanel />}
        {tab === "records" && <RecordsPanel />}
        {tab === "audit" && <AuditPanel />}
      </main>
    </div>
  );
}
