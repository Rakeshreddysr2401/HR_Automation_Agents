import { useState } from "react";
import { Badge, Button } from "../ui";
import { IconCheck, IconUndo } from "../icons";
import { Evidence } from "./Evidence";
import type { Decision, Escalation } from "../../types";

const LABELS: Record<string, string> = {
  column_mapping: "Column Mapping",
  date_convention: "Date Format",
  enum_value: "Unmapped Value",
  duplicate_suspected: "Possible Duplicate",
  rehire_suspected: "Rehire or Duplicate",
  validation_failed: "Validation Issue",
  field_unsourced: "Missing Column",
  hierarchy_orphan: "Unmatched Manager",
  hierarchy_cycle: "Reporting Loop",
  push_rejected: "Destination Rejected",
  batch_anomaly: "Batch Warning",
};

const EDIT_PROMPT: Record<string, string> = {
  validation_failed: "Supply the missing values",
  push_rejected: "Update record details",
  hierarchy_orphan: "Reassign to (work email of an employee in this migration)",
};

/**
 * One question.
 *
 * The staged/unstaged distinction matters more than it looks: answers are
 * collected locally and submitted as a batch, because every answer re-runs the
 * whole pipeline. Submitting one at a time would mean a dozen full re-analyses
 * for a queue a consultant means to work through in one sitting.
 */
export function EscalationCard({
  escalation,
  staged,
  onStage,
  onUnstage,
  focused,
  onFocus,
  index,
}: {
  escalation: Escalation;
  staged?: Decision;
  onStage: (subject: string, answer: Decision) => void;
  onUnstage: (subject: string) => void;
  focused: boolean;
  onFocus: () => void;
  index: number;
}) {
  const [edits, setEdits] = useState<Record<string, string>>({});
  const editable = (escalation.evidence.editable_fields ?? []) as string[];

  return (
    <article
      onClick={onFocus}
      className={`a-rise scroll-mt-24 overflow-hidden rounded-[var(--radius-lg)] border bg-surface
        transition-[border-color,box-shadow,opacity] duration-[var(--dur-fast)]
        ${focused
          ? "border-brand shadow-[0_0_0_3px_var(--ring)]"
          : "border-line shadow-[var(--shadow-sm)]"}
        ${staged ? "opacity-65" : ""}`}
    >
      <header className="flex items-start justify-between gap-3 border-b border-line px-[var(--panel-pad)] py-2.5">
        <div className="min-w-0">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="mono tnum text-[var(--text-xs)] text-faint">
              {String(index + 1).padStart(2, "0")}
            </span>
            <Badge tone="ask">{LABELS[escalation.type] ?? escalation.type}</Badge>
            {escalation.affected_count > 0 && (
              <Badge
                tone="neutral"
                title="One question standing for every record it covers — never one question per row."
              >
                {escalation.affected_count} record{escalation.affected_count === 1 ? "" : "s"}
              </Badge>
            )}
            {staged && (
              <Badge tone="auto">
                <IconCheck /> answered
              </Badge>
            )}
          </div>
          <h3 className="text-[15px] leading-snug font-semibold">{escalation.title}</h3>
        </div>
      </header>

      <div className="space-y-3 px-[var(--panel-pad)] py-3">
        <p className="text-[var(--text-base)] leading-relaxed text-muted">{escalation.question}</p>
        <Evidence e={escalation} />
      </div>

      {!staged && editable.length > 0 && escalation.options.some((o) => o.value === "edit") && (
        <div className="border-t border-line px-[var(--panel-pad)] py-3">
          <div className="mb-2 text-[var(--text-xs)] tracking-wide text-faint uppercase">
            {EDIT_PROMPT[escalation.type] ?? "Supply the missing values"}
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {editable.map((field) => (
              <label key={field} className="block">
                <span className="mb-0.5 block text-[var(--text-xs)] text-faint">{field}</span>
                <input
                  value={edits[field] ?? ""}
                  onChange={(event) => setEdits({ ...edits, [field]: event.target.value })}
                  placeholder={escalation.type === "hierarchy_orphan" ? "name@company.com" : "leave blank to skip"}
                  className="w-full rounded-[var(--radius-md)] border border-line bg-sunken px-2 py-1.5
                    text-[var(--text-base)] outline-none transition-colors focus:border-brand"
                />
              </label>
            ))}
          </div>
        </div>
      )}

      <footer className="flex flex-wrap items-center gap-2 border-t border-line bg-raised/40 px-[var(--panel-pad)] py-2.5">
        {staged ? (
          <>
            <span className="text-[var(--text-sm)] text-muted">
              Answered: <strong className="text-ink">{describe(staged)}</strong>
            </span>
            <div className="ml-auto">
              <Button size="sm" variant="ghost" onClick={() => onUnstage(escalation.subject)}>
                <IconUndo /> Change
              </Button>
            </div>
          </>
        ) : (
          escalation.options.map((option, position) => {
            if (option.value === "edit") {
              return (
                <Button
                  key={option.value}
                  size="sm"
                  variant="primary"
                  disabled={Object.values(edits).every((v) => !v?.trim())}
                  onClick={() => onStage(escalation.subject, { action: "edit", fields: edits })}
                  title={option.detail}
                >
                  {option.label}
                </Button>
              );
            }
            return (
              <Button
                key={option.value}
                size="sm"
                title={option.detail}
                onClick={() => onStage(escalation.subject, option.value)}
              >
                {/* The number is the keyboard shortcut for this option, shown
                    so the shortcut is discoverable rather than documented. */}
                {position < 9 && <kbd>{position + 1}</kbd>}
                {option.label}
                {option.detail && (
                  <span className="ml-0.5 text-[var(--text-xs)] font-normal text-faint">
                    {option.detail}
                  </span>
                )}
              </Button>
            );
          })
        )}
      </footer>
    </article>
  );
}

function describe(answer: Decision): string {
  if (typeof answer === "string") return answer;
  if (typeof answer === "boolean") return answer ? "yes" : "no";
  if (answer && typeof answer === "object" && answer.action === "edit") {
    const fields = Object.entries(answer.fields ?? {}).filter(([, v]) => v);
    return fields.length ? fields.map(([k, v]) => `${k} = ${v}`).join(", ") : "edited";
  }
  return JSON.stringify(answer);
}
