import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useStore } from "../state/store";
import { Badge, Button, Delta, Empty, Input, Panel, Segmented, Spinner, Stat } from "./ui";
import { IconDownload, IconRefresh, IconSearch, IconSpark } from "./icons";
import type { PlanRecord } from "../types";

/**
 * The dry run.
 *
 * The escalation queue is where the agent asks. This is where a consultant can
 * audit everything it did *not* ask about — per record, in the exact shape the
 * target will receive. The argument that most decisions shouldn't be approved
 * individually only holds if the aggregate is inspectable before it is sent.
 */
export function PlanPanel() {
  const { plan, loadPlan, runId, summary, toast } = useStore();
  const [view, setView] = useState<"send" | "held" | "sent">("send");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [recipe, setRecipe] = useState<string | null>(null);

  useEffect(() => {
    if (runId && !plan) {
      setLoading(true);
      void loadPlan().finally(() => setLoading(false));
    }
  }, [runId, plan, loadPlan]);

  if (!runId) {
    return (
      <Panel title="Preview — what will be sent" icon={<IconSpark />}>
        <Empty icon={<IconSpark />}>
          Run a migration first. This view displays the final payload for each employee record
          and every automatic fix applied before sending to the destination HRMS.
        </Empty>
      </Panel>
    );
  }

  const rows =
    (view === "send" ? plan?.will_send : view === "held" ? plan?.held_back : plan?.already_sent) ?? [];
  const visible = rows.filter((record) => {
    if (!query) return true;
    const hay = `${record.key} ${record.name} ${record.employee_code ?? ""}`.toLowerCase();
    return hay.includes(query.toLowerCase());
  });

  async function download() {
    if (!runId) return;
    try {
      const text = await api.recipeYaml(runId);
      const blob = new Blob([text], { type: "text/yaml" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `recipe_${runId}.yaml`;
      anchor.click();
      URL.revokeObjectURL(url);
      toast("auto", "Recipe exported successfully");
    } catch (error) {
      toast("ask", (error as Error).message);
    }
  }

  async function preview() {
    if (!runId) return;
    if (recipe) return setRecipe(null);
    try {
      setRecipe(await api.recipeYaml(runId));
    } catch (error) {
      toast("ask", (error as Error).message);
    }
  }

  return (
    <div className="space-y-3">
      <Panel
        title="Preview — what will be sent (nothing has been sent yet)"
        subtitle="Each employee exactly as the HRMS will receive it, plus every value the agent fixed without asking"
        icon={<IconSpark />}
        right={
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setLoading(true);
              void loadPlan().finally(() => setLoading(false));
            }}
          >
            {loading ? <Spinner /> : <IconRefresh />} Refresh
          </Button>
        }
      >
        <div className="flex flex-wrap items-center gap-6">
          <Stat label="Ready to send (passed every check)" value={plan?.totals.will_send ?? 0} tone="brand" />
          <Stat label="Held back (waiting on a question)" value={plan?.totals.held_back ?? 0} tone="ask" />
          <Stat
            label="Values fixed automatically"
            value={plan?.totals.fields_changed ?? 0}
            tone="flag"
            hint="Values automatically corrected (e.g. phone formats, dates, trimmed spaces)."
          />
          <Stat
            label="Employees with a fix"
            value={plan?.totals.records_with_changes ?? 0}
            tone="flag"
          />
          <Stat label="Already in HRMS" value={plan?.totals.already_loaded ?? 0} tone="auto" />
          {summary.elapsed_seconds != null && (
            <Stat label="Processing Time" value={`${summary.elapsed_seconds}s`} />
          )}
        </div>
      </Panel>

      <Panel
        title="Employees — click a row to see the record and its fixes"
        icon={<IconSpark />}
        flush
        right={
          <div className="flex items-center gap-2">
            <Input
              value={query}
              onChange={setQuery}
              placeholder="Search employee name or code…"
              icon={<IconSearch />}
              width="w-48"
            />
            <Segmented
              label="Which records"
              value={view}
              onChange={setView}
              options={[
                { id: "send", label: `Ready to send (${plan?.totals.will_send ?? 0})` },
                { id: "held", label: `Held back (${plan?.totals.held_back ?? 0})` },
                { id: "sent", label: `Already sent (${plan?.already_sent.length ?? 0})` },
              ]}
            />
          </div>
        }
      >
        {loading && !plan ? (
          <div className="flex items-center justify-center gap-2 py-12 text-faint">
            <Spinner /> Loading preview records…
          </div>
        ) : visible.length === 0 ? (
          <Empty>
            {view === "send"
              ? plan?.already_sent.length
                ? "Everything has been sent — see the Already sent list, or the Records tab for results."
                : "Nothing is ready to send yet — answer the open questions in the Review tab first."
              : view === "held"
                ? "No records are currently held back."
                : "Nothing has been sent yet."}
          </Empty>
        ) : (
          <ul className="divide-y divide-line-soft">
            {visible.map((record) => (
              <PlanRow key={`${record.key}-${record.sources.join()}`} record={record} held={view !== "send"} />
            ))}
          </ul>
        )}
      </Panel>

      {/* The recipe. The productisation story made concrete: this run's
          knowledge as a file the next migration can start from. */}
      <Panel
        title="Recipe — reuse these answers on the next migration"
        subtitle="A text file of every rule and answer from this run (no employee data). Paste it into Run next time and it will not ask again."
        icon={<IconDownload />}
        right={
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" onClick={() => void preview()}>
              {recipe ? "Hide" : "Preview YAML"}
            </Button>
            <Button size="sm" variant="subtle" onClick={() => void download()}>
              <IconDownload /> Download Recipe (.yaml)
            </Button>
          </div>
        }
      >
        <p className="text-[var(--text-sm)] leading-relaxed text-muted">
          Every rule this run settled on, labelled by how it was reached —{" "}
          <span className="text-auto">confirmed</span> by a person,{" "}
          <span className="text-flag">inferred</span> by the agent, or{" "}
          <span className="text-muted">automatic</span>. Rules only, never records, so it can be
          committed to a repository without a PII review. Paste it into{" "}
          <em>Start from a recipe</em> on the Run tab and the next migration of a similar export
          asks a fraction of what this one did.
        </p>
        {recipe && (
          <pre className="mono mt-3 max-h-96 overflow-auto rounded-[var(--radius-md)] border border-line bg-sunken p-3 text-[var(--text-xs)] leading-relaxed">
            {recipe}
          </pre>
        )}
      </Panel>
    </div>
  );
}

function PlanRow({ record, held }: { record: PlanRecord; held: boolean }) {
  const [open, setOpen] = useState(false);

  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 px-[var(--panel-pad)] py-[var(--row-y)] text-left transition-colors hover:bg-raised/50"
      >
        <code className="mono w-24 shrink-0 truncate text-[var(--text-sm)]">
          {record.employee_code ?? record.key}
        </code>
        <span className="w-48 shrink-0 truncate text-[var(--text-sm)] font-medium">
          {record.name || <span className="text-faint italic">unnamed</span>}
        </span>
        <span className="tnum shrink-0 text-[var(--text-xs)] text-faint">
          {Object.keys(record.payload).length} fields
        </span>
        {record.merged && (
          <Badge tone="brand" title={record.sources.join(", ")}>
            merged from {record.sources.length}
          </Badge>
        )}
        {record.changes.length > 0 && (
          <Badge tone="flag">
            {record.changes.length} fix{record.changes.length === 1 ? "" : "es"}
          </Badge>
        )}
        {record.pii_fields.length > 0 && (
          <Badge tone="neutral" title={`Masked on screen: ${record.pii_fields.join(", ")}`}>
            {record.pii_fields.length} masked (PII)
          </Badge>
        )}
        <span className="ml-auto shrink-0">
          {held ? (
            <span className="text-[var(--text-xs)] text-ask">{record.reason_held}</span>
          ) : (
            <Badge tone="brand">ready</Badge>
          )}
        </span>
      </button>

      {open && (
        <div className="a-fade grid gap-4 border-t border-line-soft bg-sunken/60 px-[var(--panel-pad)] py-3 lg:grid-cols-2">
          <div>
            <div className="mb-1.5 text-[var(--text-xs)] tracking-wide text-faint uppercase">
              Final record — exactly what the HRMS receives
            </div>
            <dl className="space-y-0.5">
              {Object.entries(record.payload).map(([field, value]) => {
                const isPii = record.pii_fields.includes(field);
                const multi = record.multi_source_fields.includes(field);
                return (
                  <div key={field} className="flex gap-2 text-[var(--text-sm)]">
                    <dt className="mono w-40 shrink-0 truncate text-faint">{field}</dt>
                    <dd className="mono min-w-0 flex-1 truncate">
                      {/* PII is masked here even though the value never went
                          near a model: a screen in an open-plan office is its
                          own exposure surface. */}
                      {isPii ? mask(String(value)) : String(value)}
                      {multi && (
                        <span
                          className="ml-1.5 text-[var(--text-xs)] text-brand"
                          title="Both source files had this field; the reconciler chose."
                        >
                          ·2 sources
                        </span>
                      )}
                    </dd>
                  </div>
                );
              })}
            </dl>
            <p className="mt-2 text-[var(--text-xs)] text-faint">
              from {record.sources.join(", ")}
            </p>
          </div>

          <div>
            <div className="mb-1.5 text-[var(--text-xs)] tracking-wide text-faint uppercase">
              Fixed automatically (before → after, and why)
            </div>
            {record.changes.length === 0 ? (
              <p className="text-[var(--text-sm)] text-faint">
                Nothing — this record arrived clean and was sent as-is.
              </p>
            ) : (
              <ul className="space-y-2">
                {record.changes.map((change, index) => (
                  <li key={index} className="text-[var(--text-sm)]">
                    <div className="flex items-center gap-2">
                      <Badge tone={change.disposition === "flagged" ? "flag" : "auto"}>
                        {change.disposition === "flagged" ? "inferred (flagged for you)" : "auto-fixed"}
                      </Badge>
                      <span className="text-muted">{change.what}</span>
                    </div>
                    <div className="mt-0.5 ml-1">
                      <Delta before={change.before} after={change.after} />
                    </div>
                    {change.why && (
                      <p className="mt-0.5 ml-1 text-[var(--text-xs)] text-faint">{change.why}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {record.errors.length > 0 && (
              <div className="mt-3">
                <div className="mb-1 text-[var(--text-xs)] tracking-wide text-faint uppercase">
                  Why it is held back
                </div>
                <ul className="space-y-0.5">
                  {record.errors.map((error, index) => (
                    <li key={index} className="text-[var(--text-sm)] text-ask">
                      {error}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

/** Keep the shape visible, hide the value. */
function mask(value: string): string {
  if (value.length <= 4) return "•".repeat(value.length);
  return `${value.slice(0, 2)}${"•".repeat(Math.max(3, value.length - 4))}${value.slice(-2)}`;
}
