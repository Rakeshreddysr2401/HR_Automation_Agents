import { useState } from "react";
import { useStore } from "../state/store";
import { Badge, Empty, Panel } from "./ui";

export function AuditPanel() {
  const { audit } = useStore();
  const [actor, setActor] = useState<"all" | "agent" | "human">("all");
  const [query, setQuery] = useState("");

  const rows = audit.filter((entry) => {
    if (actor !== "all" && entry.actor !== actor) return false;
    if (!query) return true;
    return `${entry.entity} ${entry.action} ${entry.rationale}`
      .toLowerCase()
      .includes(query.toLowerCase());
  });

  if (!audit.length) {
    return (
      <Panel title="Audit trail">
        <Empty>Every change the agent or a person makes is recorded here, with its reason.</Empty>
      </Panel>
    );
  }

  return (
    <Panel
      title={`Audit trail (${audit.length})`}
      subtitle="every change, who made it, and why"
      right={
        <div className="flex items-center gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="search…"
            className="w-36 rounded-lg border border-line bg-canvas px-2 py-1 text-[12px] outline-none focus:border-brand"
          />
          <div className="flex overflow-hidden rounded-lg border border-line">
            {(["all", "agent", "human"] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setActor(option)}
                className={`px-2 py-1 text-[11px] capitalize transition ${
                  actor === option ? "bg-brand text-white" : "bg-surface text-muted hover:bg-raised"
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        </div>
      }
    >
      <div className="max-h-[68vh] overflow-auto">
        <table className="w-full text-[12px]">
          <thead className="sticky top-0 bg-raised">
            <tr className="text-left text-[10px] tracking-wide text-faint uppercase">
              <th className="px-3 py-2 font-medium">Who</th>
              <th className="px-3 py-2 font-medium">Action</th>
              <th className="px-3 py-2 font-medium">Entity</th>
              <th className="px-3 py-2 font-medium">Change</th>
              <th className="px-3 py-2 font-medium">Why</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((entry) => (
              <tr key={entry.id} className="border-t border-line/60 align-top hover:bg-raised/40">
                <td className="px-3 py-2">
                  <Badge tone={entry.actor === "human" ? "brand" : "neutral"}>{entry.actor}</Badge>
                </td>
                <td className="px-3 py-2 whitespace-nowrap">{entry.action.replace(/_/g, " ")}</td>
                <td className="mono px-3 py-2 text-[11px] text-muted">{entry.entity}</td>
                <td className="px-3 py-2">
                  {entry.before != null && String(entry.before) !== "" && (
                    <span className="text-faint line-through">{String(entry.before)}</span>
                  )}
                  {entry.after != null && (
                    <span className="ml-1 font-medium">{String(entry.after)}</span>
                  )}
                </td>
                <td className="max-w-md px-3 py-2 text-muted">{entry.rationale}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
