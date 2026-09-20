import { useEffect } from "react";
import { useStore } from "../state/store";
import { Badge, Empty, Panel } from "./ui";
import { IconShield } from "./icons";

const TIER_TONE: Record<string, "auto" | "flag" | "ask"> = {
  auto: "auto",
  flagged: "flag",
  escalated: "ask",
};

/**
 * The escalation boundary, on screen.
 *
 * Served from `app/policy.py` rather than restated here, because the whole
 * value of keeping every threshold in one file disappears the moment a second
 * copy exists that can drift. A reviewer asking "why 0.82?" gets the real
 * number and the real reasoning, and changing the threshold changes this page
 * in the same edit.
 */
export function PolicyPanel() {
  const { policy, loadReference } = useStore();

  useEffect(() => {
    if (!policy) void loadReference();
  }, [policy, loadReference]);

  if (!policy) {
    return (
      <Panel title="Decision Rules & Policy" icon={<IconShield />}>
        <Empty icon={<IconShield />}>Loading migration policy from agent…</Empty>
      </Panel>
    );
  }

  return (
    <div className="space-y-3">
      <Panel icon={<IconShield />} title="Decision Policy & Escalation Rules" subtitle="Read live from app/policy.py — governs autonomous vs human actions">
        <blockquote
          className="rounded-[var(--radius-md)] border-l-2 border-brand bg-brand-soft/60 px-4 py-3
            text-[15px] leading-relaxed font-medium"
        >
          {policy.principle}
        </blockquote>

        <p className="mt-3 text-[var(--text-sm)] leading-relaxed text-muted">
          Not difficulty, and not the agent's confidence — both are the intuitive criteria and
          both are wrong. Trimming <code className="mono">"&nbsp;&nbsp;Engineering&nbsp;"</code> is
          safe: a wrong correction is visible immediately and costs seconds. Reading{" "}
          <code className="mono">03/04/2021</code> as 3 April rather than 4 March is not — the
          result looks valid, nothing complains, and it quietly misstates that person's tenure
          and gratuity for years. Same edit size, opposite blast radius.
        </p>

        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          {policy.tiers.map((tier) => (
            <div
              key={tier.id}
              className="rounded-[var(--radius-md)] border border-line bg-raised/50 p-3"
            >
              <Badge tone={TIER_TONE[tier.id] ?? "neutral"}>{tier.label}</Badge>
              <p className="mt-1.5 text-[var(--text-sm)] leading-relaxed text-muted">
                {tier.meaning}
              </p>
            </div>
          ))}
        </div>

        <p className="mt-3 text-[var(--text-xs)] leading-relaxed text-faint">
          Three tiers, not two. Auto-and-ask alone forces a choice between an agent that hides
          its reasoning and one that interrupts constantly. The middle tier is what keeps the
          queue short while the agent stays auditable.
        </p>
      </Panel>

      <div className="grid gap-3 lg:grid-cols-2">
        {policy.groups.map((group) => (
          <Panel key={group.id} title={group.title} flush>
            <p className="px-[var(--panel-pad)] py-2.5 text-[var(--text-sm)] leading-relaxed text-muted">
              {group.summary}
            </p>
            <ul className="divide-y divide-line-soft border-t border-line">
              {group.thresholds.map((threshold) => (
                <li
                  key={threshold.key}
                  className="px-[var(--panel-pad)] py-[var(--cell-y)]"
                >
                  <div className="flex items-baseline gap-2">
                    <span className="text-[var(--text-sm)] font-medium">{threshold.name}</span>
                    <code
                      className="mono tnum ml-auto shrink-0 rounded-[var(--radius-sm)] border border-brand/25
                        bg-brand-soft px-1.5 py-0.5 text-[var(--text-sm)] text-brand-ink"
                    >
                      {format(threshold.value)}
                    </code>
                  </div>
                  <p className="mt-0.5 text-[var(--text-xs)] leading-relaxed text-faint">
                    <code className="mono">{threshold.key}</code> — {threshold.note}
                  </p>
                </li>
              ))}
            </ul>
          </Panel>
        ))}
      </div>

      <Panel title="How these numbers were chosen">
        <p className="text-[var(--text-sm)] leading-relaxed text-muted">
          <code className="mono">scripts/sweep_thresholds.py</code> re-runs the sample migration
          across a 63-cell grid of confidence and margin values. The result is worth stating
          plainly: <strong className="text-ink">no setting in the grid produces a wrong mapping</strong>,
          including the most permissive. What is doing the work is the assignment step — columns
          compete for each target field, so ambiguity resolves structurally rather than
          numerically.
        </p>
        <p className="mt-2 text-[var(--text-sm)] leading-relaxed text-muted">
          The thresholds were kept tight anyway. A 35-column sample cannot show that a loose
          setting is safe on inputs it does not contain, only fail to find a counter-example.
          The tight defaults cost two extra questions here. That is the premium, and it is
          deliberate.
        </p>
      </Panel>
    </div>
  );
}

function format(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(2);
}
