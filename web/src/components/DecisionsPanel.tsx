import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useStore } from "../state/store";
import { Badge, Empty, Panel } from "./ui";

const ACTION_LABELS: Record<string, string> = {
  normalise_values: "Tidied spacing and casing",
  canonicalise_value: "Mapped a value onto the schema's vocabulary",
  infer_date_convention: "Worked out a date format from the column",
  merge_duplicate: "Merged rows describing one person",
  repair_value: "Repaired a malformed value",
  push_record: "Loaded into the target system",
  defer_hierarchy_check: "Deferred a check until a question is answered",
};

/**
 * Autonomy has to be inspectable or it is just opacity with better manners.
 * This view is deliberately read-only: these decisions did not need a human, and
 * turning them into a second approval queue would defeat the point. But they are
 * all here, grouped, with the reasoning attached.
 */
export function DecisionsPanel() {
  const { audit, summary } = useStore();
  const [memory, setMemory] = useState<
    { column_key: string; target: string; times_used: number }[]
  >([]);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    api.memory().then((r) => setMemory(r.memory)).catch(() => setMemory([]));
  }, [audit.length]);

  const byAgent = audit.filter((entry) => entry.actor === "agent");
  const groups = new Map<string, typeof byAgent>();
  for (const entry of byAgent) {
    const list = groups.get(entry.action) ?? [];
    list.push(entry);
    groups.set(entry.action, list);
  }

  if (!byAgent.length) {
    return (
      <Panel title="Decisions the agent made alone">
        <Empty>Run a migration to see what it settled without asking.</Empty>
      </Panel>
    );
  }

  return (
    <div className="space-y-4">
      <Panel
        title="Decisions the agent made alone"
        subtitle={`${byAgent.length} changes applied without asking — ${summary.columns_auto ?? 0} columns mapped, ${summary.columns_ignored ?? 0} left behind`}
      >
        <div className="divide-y divide-line">
          {[...groups.entries()]
            .sort((a, b) => b[1].length - a[1].length)
            .map(([action, entries]) => (
              <div key={action}>
                <button
                  type="button"
                  onClick={() => setOpen(open === action ? null : action)}
                  className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-raised/40"
                >
                  <Badge tone={entries[0].disposition === "flagged" ? "flag" : "auto"}>
                    {entries[0].disposition === "flagged" ? "inferred" : "automatic"}
                  </Badge>
                  <span className="flex-1 text-[13px]">
                    {ACTION_LABELS[action] ?? action.replace(/_/g, " ")}
                  </span>
                  <span className="mono text-[12px] text-muted">{entries.length}</span>
                  <span className="text-faint" aria-hidden>
                    {open === action ? "−" : "+"}
                  </span>
                </button>
                {open === action && (
                  <ul className="space-y-1.5 border-t border-line bg-raised/30 px-4 py-3">
                    {entries.slice(0, 12).map((entry) => (
                      <li key={entry.id} className="text-[12px]">
                        <span className="mono text-[11px] text-faint">{entry.entity}</span>
                        <span className="mx-1.5">
                          {String(entry.before ?? "") && (
                            <span className="text-faint line-through">{String(entry.before)}</span>
                          )}
                          <span className="ml-1 font-medium">{String(entry.after ?? "")}</span>
                        </span>
                        <div className="text-muted">{entry.rationale}</div>
                      </li>
                    ))}
                    {entries.length > 12 && (
                      <li className="text-[11px] text-faint">
                        …and {entries.length - 12} more, all in the audit trail.
                      </li>
                    )}
                  </ul>
                )}
              </div>
            ))}
        </div>
      </Panel>

      <Panel
        title="What it learned from you"
        subtitle="answers kept for the next file and the next client, so the same question is never asked twice"
      >
        {memory.length === 0 ? (
          <Empty>
            Nothing yet. Resolve a mapping question and it is remembered — re-run the same
            files afterwards and the agent will not ask again.
          </Empty>
        ) : (
          <ul className="divide-y divide-line">
            {memory.map((item) => (
              <li key={item.column_key} className="flex items-center gap-3 px-4 py-2 text-[13px]">
                <code className="mono">{item.column_key}</code>
                <span className="text-faint" aria-hidden>→</span>
                <span className="font-medium">{item.target}</span>
                <span className="ml-auto text-[11px] text-faint">
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
