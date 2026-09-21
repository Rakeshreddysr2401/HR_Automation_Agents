import { useMemo, useState } from "react";
import { useStore } from "../state/store";
import { Badge, Empty, Input, Meter, Panel, Segmented } from "./ui";
import { IconArrow, IconMap, IconSearch } from "./icons";
import type { Mapping } from "../types";

const DISPOSITION: Record<string, { tone: "auto" | "flag" | "ask" | "neutral"; label: string }> = {
  auto: { tone: "auto", label: "Mapped alone" },
  flagged: { tone: "flag", label: "Inferred (applied, flagged)" },
  escalated: { tone: "ask", label: "Asked you" },
  ignored: { tone: "neutral", label: "Left behind" },
};

const PROVENANCE: Record<string, string> = {
  scored: "Semantic AI matching against target schema",
  memory: "Recalled from confirmed recipe / memory",
  human: "Confirmed by migration consultant",
};

/**
 * Every source column and where it ended up.
 *
 * This is the view that answers "did it actually understand my file?" in one
 * screen, which is the first question any implementation consultant asks. It is
 * read-only by design: a mapping the agent applied without asking is exactly
 * what it claims not to need approval for, and turning this into a second
 * approval queue would undo the argument the rest of the app makes.
 */
export function MappingPanel() {
  const { mappings, schema } = useStore();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");

  const counts = useMemo(() => {
    const out: Record<string, number> = { auto: 0, flagged: 0, escalated: 0, ignored: 0 };
    for (const m of mappings) out[m.disposition] = (out[m.disposition] ?? 0) + 1;
    return out;
  }, [mappings]);

  const byFile = useMemo(() => {
    const filtered = mappings.filter((m) => {
      if (filter !== "all" && m.disposition !== filter) return false;
      if (!query) return true;
      const hay = `${m.column} ${m.target_field ?? ""} ${m.rationale}`.toLowerCase();
      return hay.includes(query.toLowerCase());
    });
    const groups = new Map<string, Mapping[]>();
    for (const m of filtered) {
      const list = groups.get(m.source_file) ?? [];
      list.push(m);
      groups.set(m.source_file, list);
    }
    return [...groups.entries()];
  }, [mappings, query, filter]);

  /** Target fields nothing reached — the gaps in the client's export. */
  const unfilled = useMemo(() => {
    if (!schema) return [];
    const hit = new Set(mappings.map((m) => m.target_field).filter(Boolean));
    return schema.fields.filter((f) => !hit.has(f.name));
  }, [schema, mappings]);

  if (!mappings.length) {
    return (
      <Panel title="Column mapping" icon={<IconMap />}>
        <Empty icon={<IconMap />}>
          Run a migration and every source column appears here with the field it reached, the
          score behind it, and why.
        </Empty>
      </Panel>
    );
  }

  return (
    <div className="space-y-3">
      <Panel
        title={`Column mapping (${mappings.length})`}
        subtitle="Every source column, the target field it became, and the evidence for it"
        icon={<IconMap />}
        flush
        right={
          <div className="flex items-center gap-2">
            <Input
              value={query}
              onChange={setQuery}
              placeholder="filter columns…"
              icon={<IconSearch />}
              width="w-44"
            />
            <Segmented
              label="Disposition"
              value={filter}
              onChange={setFilter}
              options={[
                { id: "all", label: "All" },
                { id: "auto", label: `Mapped alone (${counts.auto})` },
                { id: "flagged", label: `Inferred (${counts.flagged})` },
                { id: "escalated", label: `Asked you (${counts.escalated})` },
                { id: "ignored", label: `Left behind (${counts.ignored})` },
              ]}
            />
          </div>
        }
      >
        {byFile.length === 0 ? (
          <Empty>Nothing matches that filter.</Empty>
        ) : (
          byFile.map(([file, rows]) => (
            <div key={file}>
              <div className="mono sticky top-0 z-10 border-y border-line bg-raised px-[var(--panel-pad)] py-1 text-[var(--text-xs)] text-muted">
                {file.split("/").pop()} · {rows.length} column{rows.length === 1 ? "" : "s"}
              </div>
              <ul className="divide-y divide-line-soft">
                {rows.map((m) => (
                  <MappingRow key={`${m.source_file}:${m.column}`} mapping={m} />
                ))}
              </ul>
            </div>
          ))
        )}
      </Panel>

      {unfilled.length > 0 && (
        <Panel
          title={`Target fields with no source column (${unfilled.length})`}
          subtitle="The client's files simply do not carry these — a gap in the export, not a mapping failure"
          icon={<IconArrow />}
        >
          <div className="flex flex-wrap gap-1.5">
            {unfilled.map((field) => (
              <span
                key={field.name}
                title={field.description}
                className={`rounded-[var(--radius-md)] border px-2 py-1 text-[var(--text-xs)] ${
                  field.required
                    ? "border-ask/30 bg-ask-soft text-ask"
                    : "border-line bg-raised text-muted"
                }`}
              >
                <span className="mono">{field.name}</span>
                {field.required && <span className="ml-1 font-medium">required</span>}
              </span>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}

function MappingRow({ mapping }: { mapping: Mapping }) {
  const [open, setOpen] = useState(false);
  const tone = DISPOSITION[mapping.disposition] ?? DISPOSITION.ignored;

  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 px-[var(--panel-pad)] py-[var(--row-y)] text-left transition-colors hover:bg-raised/50"
      >
        <code className="mono w-44 shrink-0 truncate text-[var(--text-sm)]">{mapping.column}</code>
        <IconArrow className="shrink-0 text-faint" />
        <span
          className={`w-44 shrink-0 truncate text-[var(--text-sm)] ${
            mapping.target_field ? "font-medium" : "text-faint italic"
          }`}
        >
          {mapping.target_field ?? "no target field"}
        </span>
        {mapping.transform && (
          <Badge tone="brand" title="A transform was applied on the way">
            {mapping.transform.replace(/_/g, " ")}
          </Badge>
        )}
        <span className="ml-auto flex shrink-0 items-center gap-2.5">
          {mapping.provenance !== "scored" && (
            <Badge tone="brand" title={PROVENANCE[mapping.provenance]}>
              {mapping.provenance}
            </Badge>
          )}
          <Meter value={mapping.confidence} showValue />
          <Badge tone={tone.tone}>{tone.label}</Badge>
        </span>
      </button>

      {open && (
        <div className="a-fade space-y-2 border-t border-line-soft bg-sunken/60 px-[var(--panel-pad)] py-3">
          <p className="text-[var(--text-sm)] leading-relaxed text-muted">{mapping.rationale}</p>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[var(--text-xs)] text-faint">
            <span>
              confidence <span className="mono tnum text-muted">{mapping.confidence.toFixed(3)}</span>
            </span>
            <span title="How far ahead of the runner-up. The margin is what separates a confident mapping from a coin flip.">
              margin <span className="mono tnum text-muted">{mapping.margin.toFixed(3)}</span>
            </span>
            <span>{PROVENANCE[mapping.provenance]}</span>
          </div>
          {mapping.candidates.length > 1 && (
            <div>
              <div className="mb-1 text-[var(--text-xs)] tracking-wide text-faint uppercase">
                How the field candidates scored
              </div>
              <div className="space-y-1">
                {mapping.candidates.map((candidate) => (
                  <div
                    key={candidate.target_field}
                    className="flex items-center gap-2 text-[var(--text-sm)]"
                  >
                    <Meter value={candidate.score} width="w-24" />
                    <span className="mono tnum w-10 text-right text-muted">
                      {candidate.score.toFixed(2)}
                    </span>
                    <span className="truncate">{candidate.target_field}</span>
                    <span className="ml-auto shrink-0 text-[var(--text-xs)] text-faint">
                      semantic {candidate.embedding_score.toFixed(2)} · literal{" "}
                      {candidate.fuzzy_score.toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </li>
  );
}
