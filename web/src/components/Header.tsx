import { useStore, type Tab } from "../state/store";
import { Appearance } from "./Appearance";
import { RunSwitcher } from "./RunSwitcher";
import { Badge, Dot, IconButton, Stat } from "./ui";
import {
  IconAlert,
  IconBrain,
  IconList,
  IconMap,
  IconQuestion,
  IconPlay,
  IconShield,
  IconSpark,
  IconTable,
  IconClock,
  IconSearch,
} from "./icons";

const TABS: { id: Tab; label: string; icon: React.ReactNode; hint: string }[] = [
  { id: "run", label: "Run", icon: <IconPlay />, hint: "Live migration progress and file upload" },
  { id: "queue", label: "Review", icon: <IconQuestion />, hint: "Questions requiring your decision" },
  { id: "mapping", label: "Mapping", icon: <IconMap />, hint: "Source columns matched to target schema" },
  { id: "plan", label: "Preview", icon: <IconSpark />, hint: "Inspect clean records and auto-repaired fields before sending" },
  { id: "records", label: "Records", icon: <IconTable />, hint: "Migration status, retry, and rollback per employee" },
  { id: "decisions", label: "Decisions", icon: <IconList />, hint: "Rules and fixes applied automatically" },
  { id: "audit", label: "Audit", icon: <IconClock />, hint: "Complete compliance log of every change" },
  { id: "policy", label: "Rules", icon: <IconShield />, hint: "Decision rules and escalation thresholds" },
];

const STATUS: Record<string, { label: string; tone: "auto" | "flag" | "ask" | "brand" | "neutral" }> = {
  idle: { label: "Ready", tone: "neutral" },
  running: { label: "Processing Migration...", tone: "brand" },
  awaiting: { label: "Action Required", tone: "ask" },
  complete: { label: "Migration Complete", tone: "auto" },
  error: { label: "Failed", tone: "ask" },
};

export function Header() {
  const { tab, setTab, summary, escalations, status, runId, models, error, setPalette } =
    useStore();

  const mapped = (summary.columns_auto ?? 0) + (summary.columns_flagged ?? 0);
  const state = STATUS[status] ?? STATUS.idle;

  return (
    <header className="glass sticky top-0 z-30 border-b border-line">
      <div className="mx-auto max-w-[1400px] px-4 pt-2.5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="flex min-w-0 items-center gap-2.5">
            {/* The mark: the whole product in one glyph — a source column
                resolving into a target field. */}
            <span
              className="grid size-7 shrink-0 place-items-center rounded-[var(--radius-md)] text-[15px] text-[var(--s-on-brand)]"
              style={{ backgroundImage: "var(--s-grad)" }}
            >
              <IconBrain />
            </span>
            <div className="min-w-0">
              <h1 className="text-[14px] leading-tight font-semibold">HR Data Migration</h1>
              <p className="flex items-center gap-1.5 text-[var(--text-xs)] text-faint">
                <Dot tone={state.tone} pulse={status === "running"} />
                {runId ? <span className="mono truncate">{runId}</span> : "no run yet"}
                <span>· {state.label}</span>
              </p>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-4">
            <Stat
              label="Auto-Mapped"
              value={`${mapped}/${summary.columns ?? 0}`}
              tone="auto"
              hint="Columns mapped automatically by the agent. Click to inspect."
              onClick={() => setTab("mapping")}
            />
            <Stat
              label="Employees"
              value={summary.records ?? 0}
              hint="Distinct employees after reconciling files and resolving identities"
              onClick={() => setTab("records")}
            />
            <Stat
              label="Needs Review"
              value={escalations.length}
              tone={escalations.length ? "ask" : "auto"}
              hint="Questions requiring human decision"
              onClick={() => setTab("queue")}
            />
            <Stat
              label="Migrated"
              value={summary.pushed ?? 0}
              tone="brand"
              hint="Records accepted by the target HRMS"
              onClick={() => setTab("records")}
            />

            <div className="hidden h-7 w-px bg-line md:block" />

            <div className="hidden items-center gap-1.5 md:flex">
              <RunSwitcher />
              <IconButton title="Command palette (⌘K)" onClick={() => setPalette(true)}>
                <IconSearch />
              </IconButton>
              <Appearance />
            </div>
          </div>
        </div>

        {/* Model reachability. Stated plainly because the degraded path is a
            real operating mode, not an error: with no embeddings the agent
            still completes, it just asks more. */}
        {models && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge tone={models.reasoning.reachable ? "auto" : "flag"}>
              <Dot tone={models.reasoning.reachable ? "auto" : "flag"} />
              {models.reasoning.reachable ? "reasoning" : "no reasoning model"} ·{" "}
              <span className="mono">{models.reasoning.model}</span>
            </Badge>
            <Badge tone={models.embedding.reachable ? "auto" : "flag"}>
              <Dot tone={models.embedding.reachable ? "auto" : "flag"} />
              embeddings · <span className="mono">{models.embedding.model}</span>
            </Badge>
            {!models.embedding.reachable && (
              <span className="text-[var(--text-xs)] text-flag">
                lexical matching only — it will ask more than usual, which is the
                correct way to degrade
              </span>
            )}
            {summary.breaker_tripped && (
              <Badge tone="ask">
                <IconAlert /> circuit breaker tripped
              </Badge>
            )}
          </div>
        )}

        {error && (
          <p className="mt-2 flex items-start gap-2 rounded-[var(--radius-md)] border border-ask/30 bg-ask-soft px-3 py-1.5 text-[var(--text-sm)] text-ask">
            <IconAlert className="mt-0.5 shrink-0" />
            {error}
          </p>
        )}

        <nav className="mt-2.5 -mb-px flex gap-0.5 overflow-x-auto" aria-label="Views">
          {TABS.map((item) => {
            const count = item.id === "queue" ? escalations.length : 0;
            const active = tab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                title={item.hint}
                aria-current={active ? "page" : undefined}
                onClick={() => setTab(item.id)}
                className={`relative flex shrink-0 items-center gap-1.5 rounded-t-[var(--radius-md)] border-b-2 px-2.5 py-1.5
                  text-[var(--text-sm)] transition-colors duration-[var(--dur-fast)]
                  ${active
                    ? "border-brand bg-surface/60 font-medium text-ink"
                    : "border-transparent text-muted hover:bg-raised/60 hover:text-ink"}`}
              >
                <span className={active ? "text-brand" : "text-faint"}>{item.icon}</span>
                {item.label}
                {count > 0 && (
                  <span className="tnum ml-0.5 rounded-full bg-ask px-1.5 text-[10px] leading-[16px] font-semibold text-white">
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
