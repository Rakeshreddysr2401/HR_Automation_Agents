import { useMemo, useState } from "react";
import { useStore } from "../state/store";
import { Badge, Delta, Empty, Input, Panel, Segmented } from "./ui";
import { IconClock, IconDownload, IconSearch } from "./icons";
import { Button } from "./ui";

/**
 * The audit trail: every change, who made it, and why.
 *
 * Filterable by actor because the most useful question a reviewer can ask of it
 * is "show me only what a person decided" — that is the list that has to be
 * defensible to the client afterwards.
 */
export function AuditPanel() {
  const { audit, toast } = useStore();
  const [actor, setActor] = useState<"all" | "agent" | "human" | "system">("all");
  const [query, setQuery] = useState("");

  const rows = useMemo(
    () =>
      audit.filter((entry) => {
        if (actor !== "all" && entry.actor !== actor) return false;
        if (!query) return true;
        return `${entry.entity} ${entry.action} ${entry.rationale}`
          .toLowerCase()
          .includes(query.toLowerCase());
      }),
    [audit, actor, query],
  );

  const counts = useMemo(() => {
    const out = { agent: 0, human: 0, system: 0 };
    for (const entry of audit) out[entry.actor] = (out[entry.actor] ?? 0) + 1;
    return out;
  }, [audit]);

  function exportCsv() {
    const header = ["at", "actor", "action", "entity", "before", "after", "rationale"];
    const escape = (value: unknown) => `"${String(value ?? "").replace(/"/g, '""')}"`;
    const body = rows.map((entry) =>
      [entry.at, entry.actor, entry.action, entry.entity, entry.before, entry.after, entry.rationale]
        .map(escape)
        .join(","),
    );
    const blob = new Blob([[header.join(","), ...body].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "audit.csv";
    anchor.click();
    URL.revokeObjectURL(url);
    toast("auto", `Exported ${rows.length} audit rows`);
  }

  if (!audit.length) {
    return (
      <Panel title="Audit trail" icon={<IconClock />}>
        <Empty icon={<IconClock />}>
          Every change the agent or a person makes is recorded here, with its reason. PII is
          masked before it is written, so the trail is safe to hand over.
        </Empty>
      </Panel>
    );
  }

  return (
    <Panel
      title={`Audit trail (${rows.length} of ${audit.length})`}
      subtitle="Every change to every record: who made it, the value before and after, and why. Personal identifiers are masked."
      icon={<IconClock />}
      flush
      right={
        <div className="flex items-center gap-2">
          <Input
            value={query}
            onChange={setQuery}
            placeholder="search…"
            icon={<IconSearch />}
            width="w-40"
          />
          <Segmented
            label="Actor"
            value={actor}
            onChange={setActor}
            options={[
              { id: "all", label: `All ${audit.length}` },
              { id: "agent", label: `Agent ${counts.agent}` },
              { id: "human", label: `You ${counts.human}` },
              ...(counts.system ? [{ id: "system" as const, label: `System ${counts.system}` }] : []),
            ]}
          />
          <Button size="sm" variant="ghost" onClick={exportCsv}>
            <IconDownload /> CSV
          </Button>
        </div>
      }
    >
      <div className="max-h-[70vh] overflow-auto">
        <table className="w-full text-[var(--text-sm)]">
          <thead className="sticky top-0 z-10 bg-raised">
            <tr className="text-left text-[var(--text-xs)] tracking-wide text-faint uppercase">
              <th className="px-3 py-2 font-medium">When</th>
              <th className="px-3 py-2 font-medium">Who</th>
              <th className="px-3 py-2 font-medium">Action</th>
              <th className="px-3 py-2 font-medium">Record / column</th>
              <th className="px-3 py-2 font-medium">Before → after</th>
              <th className="px-3 py-2 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((entry) => (
              <tr
                key={entry.id}
                className="border-t border-line-soft align-top transition-colors hover:bg-raised/50"
              >
                <td className="mono px-3 py-[var(--cell-y)] text-[var(--text-xs)] whitespace-nowrap text-faint">
                  {entry.at.slice(11, 19)}
                </td>
                <td className="px-3 py-[var(--cell-y)]">
                  <Badge tone={entry.actor === "human" ? "brand" : "neutral"}>{entry.actor}</Badge>
                </td>
                <td className="px-3 py-[var(--cell-y)] whitespace-nowrap">
                  {entry.action.replace(/_/g, " ")}
                </td>
                <td className="mono px-3 py-[var(--cell-y)] text-[var(--text-xs)] text-muted">
                  {entry.entity}
                </td>
                <td className="px-3 py-[var(--cell-y)]">
                  <Delta before={entry.before} after={entry.after} />
                </td>
                <td className="max-w-md px-3 py-[var(--cell-y)] leading-relaxed text-muted">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span>{entry.rationale}</span>
                    {entry.disposition && (
                      <Badge
                        tone={
                          entry.disposition === "flagged"
                            ? "flag"
                            : entry.disposition === "escalated"
                              ? "ask"
                              : "auto"
                        }
                      >
                        {entry.disposition}
                      </Badge>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
