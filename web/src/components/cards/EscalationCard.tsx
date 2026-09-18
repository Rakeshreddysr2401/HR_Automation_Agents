import { useState } from "react";
import { Badge, Button } from "../ui";
import { Evidence } from "./Evidence";
import type { Decision, Escalation } from "../../types";

const LABELS: Record<string, string> = {
  column_mapping: "Mapping",
  date_convention: "Date format",
  enum_value: "Unknown value",
  duplicate_suspected: "Possible duplicate",
  rehire_suspected: "Rehire or duplicate",
  validation_failed: "Will not load",
  hierarchy_orphan: "Broken reporting line",
  hierarchy_cycle: "Reporting loop",
  push_rejected: "Target refused it",
  batch_anomaly: "Whole run",
};

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
  const isEditing =
    typeof staged === "object" && staged !== null && (staged as any).action === "edit";

  function stageEdit() {
    onStage(escalation.subject, { action: "edit", fields: edits });
  }

  return (
    <article
      onClick={onFocus}
      className={`animate-in scroll-mt-4 rounded-xl border bg-surface transition
        ${focused ? "border-brand ring-1 ring-brand/30" : "border-line"}
        ${staged ? "opacity-70" : ""}`}
    >
      <header className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="mono text-[11px] text-faint">{index + 1}</span>
            <Badge tone="ask">{LABELS[escalation.type] ?? escalation.type}</Badge>
            {escalation.affected_count > 0 && (
              <Badge tone="neutral">
                {escalation.affected_count} record{escalation.affected_count === 1 ? "" : "s"}
              </Badge>
            )}
            {staged && <Badge tone="auto">answered</Badge>}
          </div>
          <h3 className="text-[15px] font-semibold">{escalation.title}</h3>
        </div>
      </header>

      <div className="space-y-3 px-4 py-3">
        <p className="text-[13px] leading-relaxed text-muted">{escalation.question}</p>
        <Evidence e={escalation} />
      </div>

      {escalation.type === "validation_failed" && !staged && (
        <div className="border-t border-line px-4 py-3">
          <div className="mb-2 text-[10px] tracking-wide text-faint uppercase">
            Supply the missing values
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {editable.map((field) => (
              <label key={field} className="block">
                <span className="mb-0.5 block text-[11px] text-faint">{field}</span>
                <input
                  value={edits[field] ?? ""}
                  onChange={(event) =>
                    setEdits({ ...edits, [field]: event.target.value })
                  }
                  placeholder="leave blank to skip"
                  className="w-full rounded-lg border border-line bg-canvas px-2 py-1.5 text-[13px] outline-none focus:border-brand"
                />
              </label>
            ))}
          </div>
        </div>
      )}

      <footer className="flex flex-wrap items-center gap-2 border-t border-line bg-raised/40 px-4 py-2.5">
        {staged ? (
          <>
            <span className="text-[12px] text-muted">
              Answered: <strong>{describe(staged)}</strong>
            </span>
            <div className="ml-auto">
              <Button size="sm" variant="ghost" onClick={() => onUnstage(escalation.subject)}>
                Change
              </Button>
            </div>
          </>
        ) : (
          <>
            {escalation.options.map((option) => {
              if (option.value === "edit") {
                return (
                  <Button
                    key={option.value}
                    size="sm"
                    variant="primary"
                    disabled={Object.values(edits).every((v) => !v?.trim())}
                    onClick={stageEdit}
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
                  variant={option.value === "separate" ? "default" : "default"}
                  title={option.detail}
                  onClick={() => onStage(escalation.subject, option.value)}
                >
                  {option.label}
                  {option.detail && (
                    <span className="ml-1 text-[10px] text-faint">{option.detail}</span>
                  )}
                </Button>
              );
            })}
          </>
        )}
        {isEditing && null}
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
