import { Badge, Field, Meter, Samples } from "../ui";
import { IconAlert, IconArrow } from "../icons";
import type { Escalation } from "../../types";

/**
 * One evidence renderer per question type.
 *
 * The rule each of these follows: show what the agent saw, why it could not
 * choose, and how much rides on the answer — without making the reader open
 * anything else. A card that needs a second screen has failed.
 */

function Row({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-3 sm:grid-cols-2">{children}</div>;
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1 text-[var(--text-xs)] tracking-wide text-faint uppercase">{children}</div>
  );
}

/** Two source columns competing for the same target field. */
function ContestEvidence({ e }: { e: Escalation }) {
  const columns = (e.evidence.columns ?? []) as any[];
  return (
    <Row>
      {columns.map((column) => (
        <div
          key={column.column}
          className="rounded-[var(--radius-md)] border border-line bg-raised/50 p-3"
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <code className="mono text-[var(--text-base)] font-semibold">{column.column}</code>
            <Meter value={column.score} showValue />
          </div>
          <Samples values={column.sample_values ?? []} />
          <div className="mt-2 text-[var(--text-xs)] text-faint">
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
          {e.evidence.inferred_type} · {e.evidence.distinct_values} distinct · {e.evidence.rows} rows
        </Field>
      </Row>
      <div>
        <Label>Sample values</Label>
        <Samples values={e.evidence.sample_values ?? []} />
      </div>
      <div>
        <Label>How each target field scored</Label>
        <div className="space-y-1">
          {scores.map((score, index) => (
            <div
              key={score.target_field}
              className="flex items-center gap-2 text-[var(--text-sm)]"
            >
              <Meter value={score.score} width="w-24" />
              <span className="mono tnum w-10 text-right text-muted">
                {score.score.toFixed(2)}
              </span>
              <span className={`truncate ${index === 0 ? "font-medium" : ""}`}>
                {score.target_field}
              </span>
              {/* The margin is the whole argument for asking, so name it. */}
              {index === 1 && scores[0] && (
                <span className="ml-auto shrink-0 text-[var(--text-xs)] text-flag">
                  {(scores[0].score - score.score).toFixed(2)} apart
                </span>
              )}
            </div>
          ))}
        </div>
      </div>
      {e.evidence.recommendation && (
        <p className="rounded-[var(--radius-md)] border border-brand/25 bg-brand-soft px-3 py-2 text-[var(--text-sm)]">
          {e.evidence.recommendation}
          <span className="mt-0.5 block text-[var(--text-xs)] text-muted">
            A suggestion only — nothing is applied until you choose.
          </span>
        </p>
      )}
    </div>
  );
}

/**
 * The date card. Given the most visual treatment of any evidence type on
 * purpose: this is the one where a wrong answer is invisible afterwards, so the
 * two readings are spelled out in full words side by side rather than left as
 * "DMY / MDY" for the reader to decode under time pressure.
 */
function DateEvidence({ e }: { e: Escalation }) {
  const samples = (e.evidence.sample_values ?? []) as string[];
  const first = samples[0];
  return (
    <div className="space-y-3">
      <Row>
        <Field label="Column">
          <code className="mono">{e.evidence.column}</code>
          <IconArrow className="mx-1 inline text-faint" />
          {e.evidence.target_field}
        </Field>
        <Field label="Unreadable values">
          {e.evidence.ambiguous_count} of {e.evidence.total_values} · no row settles it
        </Field>
      </Row>

      <div>
        <Label>Every value is ambiguous</Label>
        <Samples values={samples} />
      </div>

      {first && (
        <div className="grid gap-2 sm:grid-cols-2">
          {(["DMY", "MDY"] as const).map((convention) => (
            <div
              key={convention}
              className="rounded-[var(--radius-md)] border border-line bg-raised/50 px-3 py-2"
            >
              <div className="text-[var(--text-xs)] text-faint">
                {convention === "DMY" ? "Read day-first" : "Read month-first"}
              </div>
              <div className="mt-0.5 text-[var(--text-base)] font-medium">
                {readAs(first, convention)}
              </div>
              <code className="mono text-[var(--text-xs)] text-faint">{first}</code>
            </div>
          ))}
        </div>
      )}

      <p className="flex items-start gap-2 rounded-[var(--radius-md)] border border-flag/25 bg-flag-soft px-3 py-2 text-[var(--text-xs)] text-flag">
        <IconAlert className="mt-0.5 shrink-0" />
        Either reading produces a valid date, so nothing downstream will complain if this is
        wrong — it would quietly distort tenure and gratuity instead. That is why it is asked
        rather than guessed.
      </p>
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
          <code className="mono rounded-[var(--radius-sm)] bg-ask-soft px-1.5 py-0.5 text-ask">
            {e.evidence.raw_value}
          </code>
        </Field>
        <Field label="Closest allowed value">
          {e.evidence.best_match}{" "}
          <span className="text-faint">({e.evidence.best_score}% similar)</span>
        </Field>
      </Row>
      <div>
        <Label>
          Affects {e.evidence.affected_rows} row(s) in {e.evidence.column}
        </Label>
        <div className="flex flex-wrap gap-1">
          {((e.evidence.allowed_values ?? []) as string[]).map((value) => (
            <span
              key={value}
              className={`rounded-full border px-2 py-0.5 text-[var(--text-xs)] ${
                value === e.evidence.best_match
                  ? "border-flag/40 bg-flag-soft text-flag"
                  : "border-line bg-raised text-muted"
              }`}
            >
              {value}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Two rows that might be one person. The highest-stakes card in the app. */
function RecordPairEvidence({ e }: { e: Escalation }) {
  const records = (e.evidence.records ?? []) as any[];
  const keys = Array.from(
    new Set(records.flatMap((r) => Object.keys(r).filter((k) => k !== "sources" && k !== "key"))),
  );
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {e.evidence.shared_pan && (
          <Badge tone="ask">Shared PAN {e.evidence.shared_pan}</Badge>
        )}
        {e.evidence.surname_similarity && (
          <Badge tone="flag">Surnames {e.evidence.surname_similarity}% alike</Badge>
        )}
      </div>
      <div className="overflow-x-auto rounded-[var(--radius-md)] border border-line">
        <table className="w-full text-[var(--text-sm)]">
          <thead>
            <tr className="border-b border-line bg-raised text-left text-[var(--text-xs)] tracking-wide text-faint uppercase">
              <th className="px-2.5 py-1.5 font-medium">Field</th>
              {records.map((r) => (
                <th key={r.key} className="mono px-2.5 py-1.5 font-medium">
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
                <tr key={key} className="border-b border-line-soft last:border-0">
                  <td className="px-2.5 py-1.5 text-faint">{key}</td>
                  {values.map((value, index) => (
                    <td
                      key={index}
                      className={`px-2.5 py-1.5 ${differs ? "bg-flag-soft/50 font-medium" : ""}`}
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
      <p className="text-[var(--text-xs)] text-faint">
        Highlighted rows are where the two disagree. Merging is unrecoverable once payroll has
        run against it; leaving a duplicate is visible and fixable.
      </p>
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
          <li key={index} className="flex gap-2 text-[var(--text-sm)] text-ask">
            <IconAlert className="mt-0.5 shrink-0" />
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
              <span className={faulty.has(key) ? "font-medium text-ask" : ""}>{String(value)}</span>
            </Field>
          ))}
      </div>
      <p className="text-[var(--text-xs)] text-faint">
        Sources: {(e.evidence.sources ?? []).join(", ")}
      </p>
    </div>
  );
}

/**
 * A required field with no source column.
 *
 * The evidence a consultant needs is not the records - it is the *field*: what
 * the schema wanted, in what shape, and how much of the file lacks it. Listing
 * the 300 affected people would be the per-record question this card exists to
 * replace.
 */
function UnsourcedFieldEvidence({ e }: { e: Escalation }) {
  const missing = Number(e.evidence.missing_records ?? 0);
  const total = Number(e.evidence.total_records ?? 0);
  return (
    <div className="space-y-3">
      <Row>
        <Field label="Field the schema requires">
          <code className="mono text-ask">{e.evidence.target_field}</code>
          <span className="ml-1.5 text-faint">({e.evidence.field_type})</span>
        </Field>
        <Field label="Records without it">
          <span className="tnum">
            {missing} of {total}
          </span>
          {total > 0 && (
            <span className="ml-1.5 text-faint">({Math.round((missing / total) * 100)}%)</span>
          )}
        </Field>
      </Row>

      {e.evidence.field_description && (
        <div>
          <Label>What the schema means by it</Label>
          <p className="text-[var(--text-sm)] leading-relaxed text-muted">
            {e.evidence.field_description}
          </p>
        </div>
      )}

      {e.evidence.format_expected && (
        <Field label="Expected shape">
          <code className="mono">{e.evidence.format_expected}</code>
        </Field>
      )}

      <p className="flex items-start gap-2 rounded-[var(--radius-md)] border border-line bg-raised/50 px-3 py-2 text-[var(--text-xs)] leading-relaxed text-muted">
        <IconAlert className="mt-0.5 shrink-0 text-flag" />
        Asked once about the field rather than once per record. Every record missing it is
        held until this is answered — so the count above is what one answer settles.
      </p>
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
      <div className="rounded-[var(--radius-md)] border border-line bg-raised/50 p-2.5">
        <Label>{reports.length} report(s) affected</Label>
        <div className="flex flex-wrap gap-1">
          {reports.map((r) => (
            <span
              key={r.key}
              className="rounded-[var(--radius-sm)] border border-line bg-surface px-1.5 py-0.5 text-[var(--text-xs)]"
            >
              {r.name} <span className="text-faint">· {r.department}</span>
            </span>
          ))}
        </div>
      </div>
      <p className="text-[var(--text-xs)] text-faint">
        Grouped by the missing manager rather than by report, so one departed manager is one
        question rather than {reports.length}.
      </p>
    </div>
  );
}

function CycleEvidence({ e }: { e: Escalation }) {
  const cycle = (e.evidence.cycle ?? []) as any[];
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {cycle.map((member) => (
        <span key={member.key} className="flex items-center gap-1.5">
          <span className="rounded-[var(--radius-md)] border border-line bg-raised px-2 py-1 text-[var(--text-sm)]">
            <strong>{member.name}</strong>
            <span className="ml-1 text-faint">{member.designation}</span>
          </span>
          <IconArrow className="text-faint" />
        </span>
      ))}
      <span className="text-[var(--text-xs)] text-ask">back to {cycle[0]?.name}</span>
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
      <div className="rounded-[var(--radius-md)] border border-ask/25 bg-ask-soft px-3 py-2 text-[var(--text-sm)] text-ask">
        {e.evidence.target_message}
      </div>
      <p className="text-[var(--text-xs)] text-faint">
        A 4xx is the target stating a business fact, not a network blip — retrying cannot fix
        it, so it is escalated instead of retried forever.
      </p>
    </div>
  );
}

function BatchEvidence({ e }: { e: Escalation }) {
  const unmapped = (e.evidence.unmapped ?? []) as string[];
  const rejectedCodes = (e.evidence.rejected_codes ?? []) as string[];
  // Three batch shapes: "wrong file" before analysis, "these two files are
  // the same people" from the identity resolver, and "the target refused most
  // of the batch for one reason" after the push.
  if (e.evidence.pair_count != null) {
    const files = (e.evidence.files ?? {}) as Record<string, number>;
    const examples = (e.evidence.examples ?? []) as string[];
    return (
      <div className="space-y-2">
        <Row>
          <Field label="Matching pairs">{e.evidence.pair_count}</Field>
          <Field label="Matched on">{String(e.evidence.basis ?? "")}</Field>
          {Object.entries(files).map(([file, rows]) => (
            <Field key={file} label={file}>{rows} rows</Field>
          ))}
        </Row>
        {examples.length > 0 && (
          <div>
            <Label>For example</Label>
            <Samples values={examples} limit={6} />
          </div>
        )}
      </div>
    );
  }
  if (e.evidence.rejected_count != null) {
    return (
      <div className="space-y-2">
        <Row>
          <Field label="Refused">
            {e.evidence.rejected_count} of {e.evidence.attempted ?? "—"} attempted
          </Field>
        </Row>
        <div className="rounded-[var(--radius-md)] border border-ask/25 bg-ask-soft px-3 py-2 text-[var(--text-sm)] text-ask">
          {e.evidence.target_message}
        </div>
        {rejectedCodes.length > 0 && (
          <div>
            <Label>Records refused{rejectedCodes.length < Number(e.evidence.rejected_count) ? " (first 20)" : ""}</Label>
            <Samples values={rejectedCodes} limit={20} />
          </div>
        )}
      </div>
    );
  }
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
          <Label>Columns with no home in the schema</Label>
          <Samples values={unmapped} limit={12} />
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
    case "field_unsourced":
      return <UnsourcedFieldEvidence e={e} />;
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
        <pre className="mono overflow-x-auto rounded-[var(--radius-md)] bg-raised p-2 text-[var(--text-xs)]">
          {JSON.stringify(e.evidence, null, 2)}
        </pre>
      );
  }
}
