import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useStore } from "../state/store";
import { Badge, Delta, Disclosure, Empty, Panel, Stat } from "./ui";
import { IconArrow, IconBrain, IconList } from "./icons";
import type { MemoryEntry } from "../types";

const ACTION_LABELS: Record<string, string> = {
  normalise_values: "Tidied spacing and casing",
  canonicalise_value: "Mapped a value onto the schema's vocabulary",
  infer_date_convention: "Worked out a date format from the column",
  set_date_convention: "Applied a date format a consultant confirmed",
  merge_duplicate: "Merged rows describing one person",
  repair_value: "Repaired a malformed value",
  push_record: "Loaded into the target system",
  defer_hierarchy_check: "Deferred a check until a question is answered",
  rollback_record: "Removed from the target system",
};

/**
 * Autonomy has to be inspectable or it is just opacity with better manners.
 *
 * This view is deliberately read-only: these are the decisions that did not
 * need a human, and turning them into a second approval queue would defeat the
 * entire point. But every one of them is here, grouped, with its reasoning.
 */
export function DecisionsPanel() {
  const { audit, summary } = useStore();
  const [memory, setMemory] = useState<MemoryEntry[]>([]);

  useEffect(() => {
    api
      .memory()
      .then((response) => setMemory(response.memory))
      .catch(() => setMemory([]));
  }, [audit.length]);

  const byAgent = audit.filter((entry) => entry.actor === "agent");
  const byHuman = audit.filter((entry) => entry.actor === "human");

  const groups = new Map<string, typeof byAgent>();
  for (const entry of byAgent) {
    const list = groups.get(entry.action) ?? [];
    list.push(entry);
    groups.set(entry.action, list);
  }

  if (!byAgent.length) {
    return (
      <Panel title="Autonomous Decisions" icon={<IconList />}>
        <Empty icon={<IconList />}>
          Run a migration to see what the system settled automatically — along with the exact reasoning
          behind each decision.
        </Empty>
      </Panel>
    );
  }

  return (
    <div className="space-y-3">
      <Panel icon={<IconList />} title="Who decided what (agent vs. you)">
        <div className="flex flex-wrap items-center gap-6">
          <Stat
            label="Decided by the agent"
            value={byAgent.length}
            tone="auto"
            hint="Changes applied automatically by deterministic rules"
          />
          <Stat
            label="Decided by you"
            value={byHuman.length}
            tone="brand"
            hint="Changes that came from human answers in the review queue"
          />
          <Stat label="Columns mapped alone" value={summary.columns_auto ?? 0} tone="auto" />
          <Stat
            label="Columns left behind (no home in schema)"
            value={summary.columns_ignored ?? 0}
            hint="Confirmed unneeded columns — safely excluded from schema"
          />
          <p className="max-w-md text-[var(--text-xs)] leading-relaxed text-faint">
            The balance is intentional: high-confidence, loud, deterministic fixes are handled
            autonomously, while high-consequence business ambiguities are escalated for human review.
          </p>
        </div>
      </Panel>

      <Panel
        title="Rules and fixes the agent applied without asking"
        subtitle={`${byAgent.length} changes, grouped by kind — each with the evidence it acted on`}
        icon={<IconList />}
        flush
      >
        <div className="divide-y divide-line-soft">
          {[...groups.entries()]
            .sort((a, b) => b[1].length - a[1].length)
            .map(([action, entries]) => (
              <Disclosure
                key={action}
                summary={
                  <span className="flex items-center gap-2.5">
                    <Badge tone={entries[0].disposition === "flagged" ? "flag" : "auto"}>
                      {entries[0].disposition === "flagged" ? "inferred" : "automatic"}
                    </Badge>
                    <span className="text-[var(--text-base)]">
                      {ACTION_LABELS[action] ?? action.replace(/_/g, " ")}
                    </span>
                  </span>
                }
                right={
                  <span className="mono tnum text-[var(--text-sm)] text-muted">
                    {entries.length}
                  </span>
                }
              >
                <ul className="space-y-2 px-[var(--panel-pad)] py-3">
                  {entries.slice(0, 12).map((entry) => (
                    <li key={entry.id} className="text-[var(--text-sm)]">
                      <div className="flex flex-wrap items-baseline gap-2">
                        <code className="mono text-[var(--text-xs)] text-faint">
                          {entry.entity}
                        </code>
                        <Delta before={entry.before} after={entry.after} />
                      </div>
                      <p className="mt-0.5 leading-relaxed text-muted">{entry.rationale}</p>
                    </li>
                  ))}
                  {entries.length > 12 && (
                    <li className="text-[var(--text-xs)] text-faint">
                      …and {entries.length - 12} more, all in the audit trail.
                    </li>
                  )}
                </ul>
              </Disclosure>
            ))}
        </div>
      </Panel>

      <Panel
        title="Remembered for next time"
        subtitle="answers kept for the next file and the next client, so the same question is never asked twice"
        icon={<IconBrain />}
        flush={memory.length > 0}
      >
        {memory.length === 0 ? (
          <Empty icon={<IconBrain />}>
            Nothing yet. Resolve a mapping question and it is remembered — re-run the same
            files afterwards and the agent will not ask again.
          </Empty>
        ) : (
          <ul className="divide-y divide-line-soft">
            {memory.map((item) => (
              <li
                key={item.column_key}
                className="flex items-center gap-3 px-[var(--panel-pad)] py-[var(--row-y)] text-[var(--text-base)]"
              >
                <code className="mono">{item.column_key}</code>
                <IconArrow className="text-faint" />
                <span className="font-medium">{item.target}</span>
                <span className="tnum ml-auto text-[var(--text-xs)] text-faint">
                  reused {item.times_used}×
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
