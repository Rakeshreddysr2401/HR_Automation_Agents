import { useStore, type Tab } from "../state/store";
import { Badge, Stat } from "./ui";

const TABS: { id: Tab; label: string }[] = [
  { id: "run", label: "Run" },
  { id: "queue", label: "Review" },
  { id: "decisions", label: "Decisions" },
  { id: "records", label: "Records" },
  { id: "audit", label: "Audit" },
];

export function Header() {
  const { tab, setTab, summary, escalations, status, runId, models, error } = useStore();

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-surface/90 backdrop-blur">
      <div className="mx-auto max-w-7xl px-4 pt-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div>
            <h1 className="text-[15px] font-semibold">HR migration</h1>
            <p className="text-[11px] text-faint">
              {runId ? <span className="mono">{runId}</span> : "no run yet"}
              {status === "awaiting" && " · waiting on you"}
              {status === "complete" && " · finished"}
            </p>
          </div>

          <div className="ml-auto flex items-center gap-5">
            <Stat
              label="mapped alone"
              value={`${(summary.columns_auto ?? 0) + (summary.columns_flagged ?? 0)}/${summary.columns ?? 0}`}
              tone="auto"
              hint="Columns the agent resolved without asking"
            />
            <Stat
              label="people"
              value={summary.records ?? 0}
              hint="Distinct employees after reconciling the files"
            />
            <Stat
              label="need you"
              value={escalations.length}
              tone={escalations.length ? "ask" : "auto"}
              hint="Questions the data genuinely cannot settle"
            />
            <Stat
              label="loaded"
              value={summary.pushed ?? 0}
              tone="brand"
              hint="Records accepted by the target system"
            />
          </div>
        </div>

        {models && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge tone={models.reasoning.reachable ? "auto" : "flag"}>
              {models.reasoning.reachable ? "model" : "no model"} · {models.reasoning.model}
            </Badge>
            <Badge tone={models.embedding.reachable ? "auto" : "flag"}>
              embeddings · {models.embedding.model}
            </Badge>
            {!models.embedding.reachable && (
              <span className="text-[11px] text-flag">
                running on lexical matching only, so it will ask more than usual
              </span>
            )}
          </div>
        )}

        {error && (
          <p className="mt-2 rounded-lg border border-ask/30 bg-ask-soft px-3 py-1.5 text-[12px] text-ask">
            {error}
          </p>
        )}

        <nav className="mt-3 flex gap-1">
          {TABS.map((item) => {
            const count = item.id === "queue" ? escalations.length : 0;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                className={`relative rounded-t-lg border-b-2 px-3 py-1.5 text-[13px] transition ${
                  tab === item.id
                    ? "border-brand text-ink"
                    : "border-transparent text-muted hover:text-ink"
                }`}
              >
                {item.label}
                {count > 0 && (
                  <span className="ml-1.5 rounded-full bg-ask px-1.5 py-0.5 text-[10px] text-white">
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
