import { useState } from "react";
import { useStore } from "../state/store";
import { Badge, Button, Empty, Input, Panel, Segmented, Spinner, Stat } from "./ui";
import type { Tone } from "./ui";
import { IconRefresh, IconSearch, IconTable, IconUndo } from "./icons";

const STATUS_TONE: Record<string, Tone> = {
  success: "auto",
  pending: "neutral",
  failed: "flag",
  rejected: "ask",
  rolled_back: "flag",
  skipped: "neutral",
};

const STATUS_HINT: Record<string, string> = {
  success: "Successfully accepted and created in destination HRMS",
  pending: "Validated and ready to be sent",
  failed: "Transient network or timeout error (retryable)",
  rejected: "Rejected by destination HRMS (e.g. duplicate employee code) — requires review",
  rolled_back: "Rolled back from destination HRMS",
  skipped: "Omitted from migration by consultant decision",
};

export function RecordsPanel() {
  const { records, retry, rollback, summary } = useStore();
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
      <Panel icon={<IconTable />} title="HRMS Integration Status">
        <div className="flex flex-wrap items-center gap-6">
          <Stat label="Total Employees" value={records.length} />
          <Stat label="Migrated to HRMS" value={pushed.length} tone="auto" />
          <Stat label="Temporary Failures" value={failed.length} tone="flag" />
          <Stat label="HRMS Rejected (4xx)" value={rejected.length} tone="ask" />
          <Stat label="Blocked by Questions" value={blocked.length} tone="ask" />
          {summary.push_rejected != null && summary.push_rejected > 0 && (
            <p className="max-w-sm text-[var(--text-xs)] leading-relaxed text-faint">
              A rejection is escalated to a human rather than retried forever: HTTP 4xx indicates a
              business rule conflict (such as an existing employee code) that needs adjudication.
            </p>
          )}
        </div>
      </Panel>

      <Panel
        title={`Records (${visible.length} of ${records.length})`}
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
                { id: "success", label: `Loaded ${pushed.length}` },
                { id: "failed", label: `Failed ${failed.length}` },
                { id: "pending", label: "Pending" },
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
                {busy ? <Spinner /> : <IconRefresh />} Retry {failed.length}
              </Button>
            )}
            {selectedPushed.length > 0 && (
              <Button size="sm" variant="danger" disabled={busy} onClick={doRollback}>
                <IconUndo /> Roll back {selectedPushed.length}
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
                <th className="px-3 py-2 font-medium">Joined</th>
                <th className="px-3 py-2 font-medium">From</th>
                <th className="px-3 py-2 font-medium">Status</th>
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
                        {record.push_status.replace(/_/g, " ")}
                      </Badge>
                      {record.blocked_by.length > 0 && (
                        <Badge tone="ask">blocked</Badge>
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
