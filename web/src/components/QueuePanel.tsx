import { useEffect, useMemo, useState } from "react";
import { useStore } from "../state/store";
import { EscalationCard } from "./cards/EscalationCard";
import { Badge, Button, Empty, Panel, Segmented, Spinner } from "./ui";
import { IconCheck, IconQuestion } from "./icons";

const GROUP_LABEL: Record<string, string> = {
  column_mapping: "Mapping",
  date_convention: "Dates",
  enum_value: "Dropdown Values",
  duplicate_suspected: "Identity",
  rehire_suspected: "Identity",
  validation_failed: "Validation",
  field_unsourced: "Missing Columns",
  hierarchy_orphan: "Hierarchy",
  hierarchy_cycle: "Hierarchy",
  push_rejected: "Integration",
  batch_anomaly: "Batch Alerts",
};

export function QueuePanel() {
  const { escalations, draft, stage, unstage, submit, submitting, focused, setFocused, round } =
    useStore();
  const [filter, setFilter] = useState<string>("all");

  const groups = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of escalations) {
      const label = GROUP_LABEL[item.type] ?? "Other";
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [escalations]);

  const visible = useMemo(
    () =>
      filter === "all"
        ? escalations
        : escalations.filter((e) => (GROUP_LABEL[e.type] ?? "Other") === filter),
    [escalations, filter],
  );

  const answered = Object.keys(draft).length;
  const total = escalations.length;

  /**
   * Keyboard triage. A consultant working a real migration is not going to
   * mouse through a hundred cards: j/k walks the queue, number keys pick an
   * option on the focused card, u undoes, and ⌘↵ sends everything answered.
   */
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      if (target?.tagName === "INPUT" || target?.tagName === "TEXTAREA") return;
      if (!visible.length) return;

      if (event.key === "j" || event.key === "ArrowDown") {
        event.preventDefault();
        setFocused(Math.min(focused + 1, visible.length - 1));
      } else if (event.key === "k" || event.key === "ArrowUp") {
        event.preventDefault();
        setFocused(Math.max(focused - 1, 0));
      } else if (event.key === "u") {
        const current = visible[focused];
        if (current) unstage(current.subject);
      } else if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        void submit();
      } else if (/^[1-9]$/.test(event.key)) {
        const current = visible[focused];
        const option = current?.options[Number(event.key) - 1];
        if (option && option.value !== "edit") {
          stage(current.subject, option.value);
          // Advance automatically: answering and then having to press j is one
          // keystroke too many when there are forty of these.
          setFocused(Math.min(focused + 1, visible.length - 1));
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visible, focused, setFocused, stage, unstage, submit]);

  useEffect(() => {
    document
      .getElementById(`card-${focused}`)
      ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [focused]);

  if (!total) {
    return (
      <Panel title="Review Queue" icon={<IconQuestion />}>
        <Empty icon={<IconCheck />}>
          All checks passed! No human review required. Anything the agent could settle from the
          data, it resolved automatically — and the Decisions tab shows exactly what that was.
        </Empty>
      </Panel>
    );
  }

  return (
    <div className="space-y-3">
      <div className="glass sticky top-[126px] z-20 flex flex-wrap items-center gap-3 rounded-[var(--radius-lg)] border border-line px-[var(--panel-pad)] py-2.5 shadow-[var(--shadow-sm)]">
        <div className="flex items-center gap-2.5">
          <div className="text-[var(--text-base)]">
            <strong className="tnum">{answered}</strong>
            <span className="text-muted"> of </span>
            <strong className="tnum">{total}</strong>
            <span className="text-muted"> answered</span>
          </div>
          <div className="h-1.5 w-28 overflow-hidden rounded-full bg-line">
            <div
              className="h-full rounded-full bg-auto transition-[width] duration-500"
              style={{ width: `${total ? (answered / total) * 100 : 0}%` }}
            />
          </div>
        </div>

        {groups.length > 1 && (
          <Segmented
            label="Filter by category"
            value={filter}
            onChange={(id) => {
              setFilter(id);
              setFocused(0);
            }}
            options={[
              { id: "all", label: `All (${total})` },
              ...groups.map(([label, count]) => ({ id: label, label: `${label} (${count})` })),
            ]}
          />
        )}

        <div className="ml-auto flex items-center gap-3">
          <span className="hidden items-center gap-1.5 text-[var(--text-xs)] text-faint lg:flex">
            <kbd>j</kbd>
            <kbd>k</kbd> move
            <kbd>1</kbd>–<kbd>9</kbd> choose
            <kbd>u</kbd> undo
            <kbd>⌘</kbd>
            <kbd>↵</kbd> apply
          </span>
          <Button
            variant="primary"
            disabled={answered === 0 || submitting}
            onClick={() => void submit()}
          >
            {submitting ? (
              <>
                <Spinner /> Processing…
              </>
            ) : (
              <>
                <IconCheck /> Confirm & Apply {answered} Decision{answered === 1 ? "" : "s"}
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Why the queue is this short, said once at the top rather than in a
          tooltip: the ratio is the entire point of the exercise. */}
      <p className="px-1 text-[var(--text-xs)] text-faint">
        Every item here is an ambiguity where the data genuinely supports more than one answer.
        Each question stands for all the records it covers — e.g. one date question, not twenty-one.
      </p>

      {/* A second-round question is not the agent changing its mind. Answers
          unlock checks that were held back on purpose - the reporting tree
          cannot be verified until the email columns are known - so say so, or
          the new card looks like a bug. */}
      {round > 1 && (
        <p className="rounded-[var(--radius-md)] border border-brand/30 bg-brand-soft px-3 py-2 text-[var(--text-sm)] text-ink">
          <strong>Review round {round}.</strong> These questions could not be asked earlier —
          your previous answers settled what the agent needed to run further checks
          (which field a losing column feeds, reporting lines, and validation that was on hold).
        </p>
      )}

      <div className="space-y-2.5">
        {visible.map((escalation, index) => (
          <div key={escalation.id} id={`card-${index}`}>
            <EscalationCard
              escalation={escalation}
              index={escalations.indexOf(escalation)}
              staged={draft[escalation.subject]}
              onStage={stage}
              onUnstage={unstage}
              focused={index === focused}
              onFocus={() => setFocused(index)}
            />
          </div>
        ))}
      </div>

      {answered > 0 && (
        <div className="flex items-center justify-center gap-2 py-2">
          <Badge tone="auto">{answered} selected</Badge>
          <span className="text-[var(--text-xs)] text-faint">
            Applying re-runs the validation engine with your answers to verify downstream records.
          </span>
        </div>
      )}
    </div>
  );
}
