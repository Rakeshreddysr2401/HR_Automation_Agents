import { useEffect } from "react";
import { useStore } from "../state/store";
import { EscalationCard } from "./cards/EscalationCard";
import { Button, Empty, Panel } from "./ui";

export function QueuePanel() {
  const {
    escalations, draft, stage, unstage, submit, submitting, focused, setFocused,
  } = useStore();

  const answered = Object.keys(draft).length;
  const total = escalations.length;

  /**
   * Keyboard triage. A consultant working a real migration is not going to
   * mouse through a hundred cards: j/k walks the queue, number keys pick an
   * option on the focused card, and Enter sends everything answered so far.
   */
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      if (target?.tagName === "INPUT" || target?.tagName === "TEXTAREA") return;
      if (!escalations.length) return;

      if (event.key === "j" || event.key === "ArrowDown") {
        event.preventDefault();
        setFocused(Math.min(focused + 1, escalations.length - 1));
      } else if (event.key === "k" || event.key === "ArrowUp") {
        event.preventDefault();
        setFocused(Math.max(focused - 1, 0));
      } else if (event.key === "u") {
        unstage(escalations[focused]?.subject);
      } else if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
        void submit();
      } else if (/^[1-9]$/.test(event.key)) {
        const current = escalations[focused];
        const option = current?.options[Number(event.key) - 1];
        if (option && option.value !== "edit") stage(current.subject, option.value);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [escalations, focused, setFocused, stage, unstage, submit]);

  useEffect(() => {
    document.getElementById(`card-${focused}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [focused]);

  if (!total) {
    return (
      <Panel title="Review queue">
        <Empty>
          Nothing is waiting on you. Anything the agent could settle from the data, it did.
        </Empty>
      </Panel>
    );
  }

  return (
    <div className="space-y-3">
      <div className="sticky top-0 z-10 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface/95 px-4 py-2.5 backdrop-blur">
        <div className="text-[13px]">
          <strong>{answered}</strong> of <strong>{total}</strong> answered
        </div>
        <div className="h-1.5 w-32 overflow-hidden rounded-full bg-line">
          <div
            className="h-full rounded-full bg-auto transition-all"
            style={{ width: `${total ? (answered / total) * 100 : 0}%` }}
          />
        </div>
        <div className="ml-auto flex items-center gap-3">
          <span className="hidden items-center gap-1.5 text-[11px] text-faint sm:flex">
            <kbd>j</kbd>
            <kbd>k</kbd> move
            <kbd>1-9</kbd> choose
            <kbd>u</kbd> undo
          </span>
          <Button
            variant="primary"
            disabled={answered === 0 || submitting}
            onClick={() => void submit()}
          >
            {submitting ? "Sending…" : `Apply ${answered} decision${answered === 1 ? "" : "s"}`}
          </Button>
        </div>
      </div>

      <div className="space-y-3">
        {escalations.map((escalation, index) => (
          <div key={escalation.id} id={`card-${index}`}>
            <EscalationCard
              escalation={escalation}
              index={index}
              staged={draft[escalation.subject]}
              onStage={stage}
              onUnstage={unstage}
              focused={index === focused}
              onFocus={() => setFocused(index)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
