import { Badge, Field, Meter, Samples } from "../ui";
import type { Escalation } from "../../types";

/**
 * One evidence renderer per question type.
 *
 * The rule each of these follows: show what the agent saw, why it could not
 * choose, and how much rides on the answer - without making the reader open
 * anything else. A card that needs a second screen has failed.
 */

function Row({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-3 sm:grid-cols-2">{children}</div>;
}

function ContestEvidence({ e }: { e: Escalation }) {
  const columns = (e.evidence.columns ?? []) as any[];
  return (
    <Row>
      {columns.map((column) => (
        <div key={column.column} className="rounded-lg border border-line bg-raised/50 p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <code className="mono text-[13px] font-semibold">{column.column}</code>
            <div className="flex items-center gap-1.5">
              <Meter value={column.score} />
              <span className="mono text-[11px] text-muted">{column.score?.toFixed(2)}</span>
            </div>
          </div>
          <Samples values={column.sample_values ?? []} />
          <div className="mt-2 text-[11px] text-faint">
            {column.distinct_values} distinct
            {column.null_rate > 0 && ` · ${Math.round(column.null_rate * 100)}% empty`}
          </div>
        </div>
      ))}
    </Row>
  );
}

function MappingEvidence({ e }: { e: Escalation }) {
  const scores = (e.evidence.scores ?? []) as any[];
  return (
    <div className="space-y-3">
      <Row>
        <Field label="Column">
          <code className="mono">{e.evidence.column}</code>
        </Field>
        <Field label="Looks like">
          {e.evidence.inferred_type} · {e.evidence.distinct_values} distinct ·{" "}
          {e.evidence.rows} rows
        </Field>
      </Row>
      <div>
        <div className="mb-1 text-[10px] tracking-wide text-faint uppercase">Sample values</div>
        <Samples values={e.evidence.sample_values ?? []} />
      </div>
      <div>
        <div className="mb-1 text-[10px] tracking-wide text-faint uppercase">
          How each target field scored
        </div>
        <div className="space-y-1">
          {scores.map((score) => (
            <div key={score.target_field} className="flex items-center gap-2 text-[12px]">
              <Meter value={score.score} />
              <span className="mono w-11 text-right text-muted">{score.score.toFixed(2)}</span>
              <span className="truncate">{score.target_field}</span>
            </div>
          ))}
        </div>
      </div>
      {e.evidence.recommendation && (
        <p className="rounded-lg border border-brand/25 bg-brand-soft px-3 py-2 text-[12px]">
          {e.evidence.recommendation}
          <span className="mt-0.5 block text-[11px] text-muted">
            A suggestion only — nothing is applied until you choose.
          </span>
        </p>
      )}
    </div>
  );
}

function DateEvidence({ e }: { e: Escalation }) {
  const samples = (e.evidence.sample_values ?? []) as string[];
  return (
    <div className="space-y-3">
      <Row>
        <Field label="Column">
          <code className="mono">{e.evidence.column}</code> → {e.evidence.target_field}
        </Field>
        <Field label="Unreadable values">
          {e.evidence.ambiguous_count} of {e.evidence.total_values} · no row settles it
        </Field>
      </Row>
      <div>
        <div className="mb-1 text-[10px] tracking-wide text-faint uppercase">
          Every value is ambiguous
        </div>
        <Samples values={samples} />
      </div>
      {samples[0] && (
        <div className="rounded-lg border border-line bg-raised/50 px-3 py-2 text-[12px]">
          <code className="mono">{samples[0]}</code> is either{" "}
          <strong>{readAs(samples[0], "DMY")}</strong> or <strong>{readAs(samples[0], "MDY")}</strong>.
        </div>
      )}
    </div>
  );
}

function readAs(value: string, convention: "DMY" | "MDY"): string {
  const parts = value.split(/[-/.]/).map((p) => parseInt(p, 10));
  if (parts.length !== 3 || parts.some(isNaN)) return value;
  const [a, b, year] = parts;
  const day = convention === "DMY" ? a : b;
  const month = convention === "DMY" ? b : a;
  const names = ["", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"];
  return `${day} ${names[month] ?? month} ${year}`;
}

function EnumEvidence({ e }: { e: Escalation }) {
  return (
    <div className="space-y-3">
      <Row>
        <Field label="Found in the data">
          <code className="mono rounded bg-ask-soft px-1.5 py-0.5 text-ask">
            {e.evidence.raw_value}
          </code>
        </Field>
        <Field label="Closest allowed value">
          {e.evidence.best_match}{" "}
          <span className="text-faint">({e.evidence.best_score}% similar)</span>
        </Field>
      </Row>
      <Field label={`Affects ${e.evidence.affected_rows} row(s) in ${e.evidence.column}`}>
        <span className="text-faint">
          Allowed: {(e.evidence.allowed_values ?? []).join(", ")}
        </span>
      </Field>
    </div>
  );
}

function RecordPairEvidence({ e }: { e: Escalation }) {
  const records = (e.evidence.records ?? []) as any[];
  const keys = Array.from(
    new Set(records.flatMap((r) => Object.keys(r).filter((k) => k !== "sources" && k !== "key"))),
  );
  return (
    <div className="space-y-3">
      {e.evidence.shared_pan && (
        <Badge tone="ask">Shared PAN {e.evidence.shared_pan}</Badge>
      )}
      {e.evidence.surname_similarity && (
        <Badge tone="flag">Surnames {e.evidence.surname_similarity}% alike</Badge>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-b border-line text-left text-[10px] tracking-wide text-faint uppercase">
              <th className="py-1.5 pr-3 font-medium">Field</th>
              {records.map((r) => (
                <th key={r.key} className="py-1.5 pr-3 font-medium">
                  {r.key}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => {
              const values = records.map((r) => String(r[key] ?? ""));
              const differs = new Set(values).size > 1;
              return (
                <tr key={key} className="border-b border-line/50 last:border-0">
                  <td className="py-1.5 pr-3 text-faint">{key}</td>
                  {values.map((value, index) => (
                    <td
                      key={index}
                      className={`py-1.5 pr-3 ${differs ? "bg-flag-soft/40 font-medium" : ""}`}
                    >
                      {value || <span className="text-faint">—</span>}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-faint">Highlighted rows are where the two disagree.</p>
    </div>
  );
}

function ValidationEvidence({ e }: { e: Escalation }) {
  const record = (e.evidence.record ?? {}) as Record<string, string>;
  const faulty = new Set((e.evidence.editable_fields ?? []) as string[]);
  return (
    <div className="space-y-3">
      <ul className="space-y-1">
        {((e.evidence.issues ?? []) as string[]).map((issue, index) => (
          <li key={index} className="flex gap-2 text-[12px] text-ask">
            <span aria-hidden>✕</span>
            <span>{issue}</span>
          </li>
        ))}
      </ul>
      <div className="grid gap-x-4 gap-y-1.5 sm:grid-cols-3">
        {Object.entries(record)
          .filter(([, value]) => value !== "" && value != null)
          .slice(0, 12)
          .map(([key, value]) => (
            <Field key={key} label={key}>
              <span className={faulty.has(key) ? "text-ask" : ""}>{String(value)}</span>
            </Field>
          ))}
      </div>
      <p className="text-[11px] text-faint">Sources: {(e.evidence.sources ?? []).join(", ")}</p>
    </div>
  );
}

function OrphanEvidence({ e }: { e: Escalation }) {
  const reports = (e.evidence.reports ?? []) as any[];
  return (
    <div className="space-y-2">
      <Field label="Manager who is in no file">
        <code className="mono text-ask">{e.evidence.missing_manager}</code>
      </Field>
      <div className="rounded-lg border border-line bg-raised/50 p-2">
        <div className="mb-1 text-[10px] tracking-wide text-faint uppercase">
          {reports.length} report(s) affected
        </div>
        <div className="flex flex-wrap gap-1">
          {reports.map((r) => (
            <span key={r.key} className="rounded border border-line bg-surface px-1.5 py-0.5 text-[11px]">
              {r.name} <span className="text-faint">· {r.department}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function CycleEvidence({ e }: { e: Escalation }) {
  const cycle = (e.evidence.cycle ?? []) as any[];
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {cycle.map((member) => (
          <span key={member.key} className="flex items-center gap-2">
            <span className="rounded-lg border border-line bg-raised px-2 py-1 text-[12px]">
              <strong>{member.name}</strong>
              <span className="ml-1 text-faint">{member.designation}</span>
            </span>
            <span className="text-faint" aria-hidden>→</span>
          </span>
        ))}
        <span className="text-[11px] text-ask">back to {cycle[0]?.name}</span>
      </div>
    </div>
  );
}

function PushRejectedEvidence({ e }: { e: Escalation }) {
  return (
    <div className="space-y-2">
      <Row>
        <Field label="Employee">{e.evidence.employee_code}</Field>
        <Field label="Target responded">HTTP {e.evidence.status_code}</Field>
      </Row>
      <div className="rounded-lg border border-ask/25 bg-ask-soft px-3 py-2 text-[12px] text-ask">
        {e.evidence.target_message}
      </div>
    </div>
  );
}

function BatchEvidence({ e }: { e: Escalation }) {
  const unmapped = (e.evidence.unmapped ?? []) as string[];
  return (
    <div className="space-y-2">
      <Row>
        <Field label="Columns recognised">
          {e.evidence.mapped_columns ?? "—"} of {e.evidence.total_columns ?? "—"}
        </Field>
        <Field label="Records needing a person">
          {e.evidence.blocked_records ?? 0} of {e.evidence.total_records ?? 0}
        </Field>
      </Row>
      {unmapped.length > 0 && (
        <div>
          <div className="mb-1 text-[10px] tracking-wide text-faint uppercase">
            Columns with no home in the schema
          </div>
          <Samples values={unmapped} />
        </div>
      )}
    </div>
  );
}

export function Evidence({ e }: { e: Escalation }) {
  switch (e.type) {
    case "column_mapping":
      return e.evidence.contest ? <ContestEvidence e={e} /> : <MappingEvidence e={e} />;
    case "date_convention":
      return <DateEvidence e={e} />;
    case "enum_value":
      return <EnumEvidence e={e} />;
    case "duplicate_suspected":
    case "rehire_suspected":
      return <RecordPairEvidence e={e} />;
    case "validation_failed":
      return <ValidationEvidence e={e} />;
    case "hierarchy_orphan":
      return <OrphanEvidence e={e} />;
    case "hierarchy_cycle":
      return <CycleEvidence e={e} />;
    case "push_rejected":
      return <PushRejectedEvidence e={e} />;
    case "batch_anomaly":
      return <BatchEvidence e={e} />;
    default:
      return (
        <pre className="mono overflow-x-auto rounded-lg bg-raised p-2 text-[11px]">
          {JSON.stringify(e.evidence, null, 2)}
        </pre>
      );
  }
}
