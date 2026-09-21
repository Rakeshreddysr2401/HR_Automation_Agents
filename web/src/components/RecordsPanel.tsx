import { useState } from "react";
import { useStore } from "../state/store";
import { Badge, Button, Empty, Input, Panel, Segmented, Spinner, Stat } from "./ui";
import type { Tone } from "./ui";
import { IconDownload, IconRefresh, IconSearch, IconTable, IconUndo } from "./icons";

const STATUS_TONE: Record<string, Tone> = {
  success: "auto",
  pending: "neutral",
  failed: "flag",
  rejected: "ask",
  rolled_back: "flag",
  skipped: "neutral",
};

const STATUS_HINT: Record<string, string> = {
  success: "Accepted and created in the HRMS",
  pending: "Passed every check; will be sent once the review queue is empty",
  failed: "Network timeout or server error — nothing wrong with the record, safe to retry",
  rejected: "The HRMS said no for a business reason (e.g. employee code already exists) — see Review",
  rolled_back: "Removed from the HRMS by you; tick it to push again",
  skipped: "You chose not to migrate this record",
};

// Plain words on the badge; the technical status stays in the tooltip.
const STATUS_LABEL: Record<string, string> = {
  success: "loaded",
  pending: "waiting to send",
  failed: "failed (can retry)",
  rejected: "rejected by HRMS",
  rolled_back: "rolled back",
  skipped: "skipped",
};

export function RecordsPanel() {
  const { records, retry, rollback, summary, runId } = useStore();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [status, setStatus] = useState("all");
  const [busy, setBusy] = useState(false);

  const visible = records.filter((record) => {
    if (status !== "all" && record.push_status !== status) return false;
    if (!filter) return true;
    const haystack = `${record.key} ${Object.values(record.fields).join(" ")}`.toLowerCase();
    return haystack.includes(filter.toLowerCase());
  });

  const failed = records.filter((r) => r.push_status === "failed");
  const pushed = records.filter((r) => r.push_status === "success");
  const rejected = records.filter((r) => r.push_status === "rejected");
  const blocked = records.filter((r) => r.blocked_by.length > 0);
  const byKey = new Map(records.map((r) => [r.key, r]));
  const selectedPushed = [...selected].filter((k) => byKey.get(k)?.push_status === "success");
  const selectedRolledBack = [...selected].filter(
    (k) => byKey.get(k)?.push_status === "rolled_back",
  );

  function toggle(key: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function doRollback() {
    // A reason is mandatory, server-side too: a rollback with no recorded
    // cause is exactly the audit gap this whole trail exists to prevent.
    const reason = window.prompt(
      "Why are these being rolled back? This reason will be logged in the audit trail.",
    );
    if (!reason?.trim()) return;
    setBusy(true);
    try {
      await rollback(selectedPushed, reason.trim());
      setSelected(new Set());
    } finally {
      setBusy(false);
    }
  }

  async function doPushAgain() {
    setBusy(true);
    try {
      await retry(selectedRolledBack);
      setSelected(new Set());
    } finally {
      setBusy(false);
    }
  }

  if (!records.length) {
    return (
      <Panel title="Records" icon={<IconTable />}>
        <Empty icon={<IconTable />}>
          No records yet. Run a migration and every reconciled employee will appear here with
          live push status, retry options, and rollback controls.
        </Empty>
      </Panel>
    );
  }

  return (
    <div className="space-y-3">
      <Panel
        icon={<IconTable />}
        title="Push results — what happened in the HRMS"
        right={
          runId && (
            <div className="flex items-center gap-1.5">
              <a
                href={`/api/runs/${runId}/export?format=xlsx`}
                className="inline-flex items-center gap-1 rounded-[var(--radius-md)] border border-line px-2 py-1 text-[var(--text-xs)] text-ink hover:bg-raised"
                title="Every employee in the target schema, with the result and source rows. Real values, not masked."
              >
                <IconDownload /> Download results (Excel)
              </a>
              <a
                href={`/api/runs/${runId}/export?format=csv`}
                className="inline-flex items-center gap-1 rounded-[var(--radius-md)] border border-line px-2 py-1 text-[var(--text-xs)] text-ink hover:bg-raised"
              >
                <IconDownload /> CSV
              </a>
              <a
                href="/mock-target/v1/employees"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-[var(--radius-md)] border border-line px-2 py-1 text-[var(--text-xs)] text-muted hover:bg-raised"
                title="What the mock HRMS actually holds right now (raw JSON)"
              >
                View in mock HRMS ↗
              </a>
            </div>
          )
        }
      >
        <div className="flex flex-wrap items-center gap-6">
          <Stat label="Employees (after merging)" value={records.length} />
          <Stat label="Loaded into HRMS" value={pushed.length} tone="auto" />
          <Stat label="Temporary failures (can retry)" value={failed.length} tone="flag" />
          <Stat label="Rejected by HRMS (needs your decision)" value={rejected.length} tone="ask" />
          <Stat label="Held by open questions" value={blocked.length} tone="ask" />
          {summary.push_rejected != null && summary.push_rejected > 0 && (
            <p className="max-w-sm text-[var(--text-xs)] leading-relaxed text-faint">
              A rejection is a business answer from the HRMS ("this employee code already exists"),
              so retrying would get the same answer. It is sent back to Review for you to decide.
            </p>
          )}
        </div>
      </Panel>

      <Panel
        title={`Employees (${visible.length} of ${records.length}) — tick loaded rows to roll back`}
        icon={<IconTable />}
        flush
        right={
          <div className="flex items-center gap-2">
            <Input
              value={filter}
              onChange={setFilter}
              placeholder="filter…"
              icon={<IconSearch />}
              width="w-36"
            />
            <Segmented
              label="Push status"
              value={status}
              onChange={setStatus}
              options={[
                { id: "all", label: "All" },
                { id: "success", label: `Loaded (${pushed.length})` },
                { id: "failed", label: `Failed (${failed.length})` },
                { id: "pending", label: "Waiting" },
                { id: "rolled_back", label: "Rolled back" },
              ]}
            />
            {failed.length > 0 && (
              <Button
                size="sm"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await retry();
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {busy ? <Spinner /> : <IconRefresh />} Retry {failed.length} failed
              </Button>
            )}
            {selectedPushed.length > 0 && (
              <Button size="sm" variant="danger" disabled={busy} onClick={doRollback}>
                <IconUndo /> Roll back {selectedPushed.length} (remove from HRMS)
              </Button>
            )}
            {selectedRolledBack.length > 0 && (
              <Button size="sm" disabled={busy} onClick={doPushAgain}>
                <IconRefresh /> Push again {selectedRolledBack.length}
              </Button>
            )}
          </div>
        }
      >
        <div className="max-h-[66vh] overflow-auto">
          <table className="w-full text-[var(--text-sm)]">
            <thead className="sticky top-0 z-10 bg-raised">
              <tr className="text-left text-[var(--text-xs)] tracking-wide text-faint uppercase">
                <th className="w-8 px-3 py-2" />
                <th className="px-3 py-2 font-medium">Code</th>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Department</th>
                <th className="px-3 py-2 font-medium">Joining date</th>
                <th className="px-3 py-2 font-medium">Source files</th>
                <th className="px-3 py-2 font-medium">Result in HRMS</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((record, index) => (
                <tr
                  key={`${record.key}-${index}`}
                  className="border-t border-line-soft transition-colors hover:bg-raised/50"
                >
                  <td className="px-3 py-[var(--cell-y)]">
                    {(record.push_status === "success" || record.push_status === "rolled_back") && (
                      <input
                        type="checkbox"
                        checked={selected.has(record.key)}
                        onChange={() => toggle(record.key)}
                        aria-label={`select ${record.key}`}
                        className="accent-[var(--s-brand)]"
                      />
                    )}
                  </td>
                  <td className="mono px-3 py-[var(--cell-y)]">
                    {record.fields.employee_code ?? record.key}
                  </td>
                  <td className="px-3 py-[var(--cell-y)]">
                    {record.fields.first_name} {record.fields.last_name}
                  </td>
                  <td className="px-3 py-[var(--cell-y)] text-muted">
                    {record.fields.department ?? "—"}
                  </td>
                  <td className="mono px-3 py-[var(--cell-y)] text-muted">
                    {record.fields.date_of_joining ?? "—"}
                  </td>
                  <td className="px-3 py-[var(--cell-y)] text-faint" title={record.sources.join(", ")}>
                    {record.sources.length > 1 ? (
                      <span className="text-brand">{record.sources.length} files</span>
                    ) : (
                      "1 file"
                    )}
                  </td>
                  <td className="px-3 py-[var(--cell-y)]">
                    <span className="flex flex-wrap items-center gap-1.5">
                      <Badge
                        tone={STATUS_TONE[record.push_status] ?? "neutral"}
                        title={STATUS_HINT[record.push_status]}
                      >
                        {STATUS_LABEL[record.push_status] ?? record.push_status.replace(/_/g, " ")}
                      </Badge>
                      {record.blocked_by.length > 0 && (
                        <Badge tone="ask">held by a question</Badge>
                      )}
                      {record.push_detail && (
                        <span className="text-[var(--text-xs)] text-faint">
                          {record.push_detail}
                        </span>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
