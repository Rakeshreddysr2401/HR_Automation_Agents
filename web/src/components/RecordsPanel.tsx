import { useState } from "react";
import { useStore } from "../state/store";
import { Badge, Button, Empty, Panel } from "./ui";
import type { Tone } from "./ui";

const STATUS_TONE: Record<string, Tone> = {
  success: "auto",
  pending: "neutral",
  failed: "flag",
  rejected: "ask",
  rolled_back: "flag",
  skipped: "neutral",
};

export function RecordsPanel() {
  const { records, retry, rollback } = useStore();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);

  const visible = records.filter((record) => {
    if (!filter) return true;
    const haystack = `${record.key} ${Object.values(record.fields).join(" ")}`.toLowerCase();
    return haystack.includes(filter.toLowerCase());
  });

  const failed = records.filter((r) => r.push_status === "failed");
  const pushed = records.filter((r) => r.push_status === "success");

  function toggle(key: string) {
    const next = new Set(selected);
    next.has(key) ? next.delete(key) : next.add(key);
    setSelected(next);
  }

  async function doRollback() {
    const reason = window.prompt(
      "Why are these being rolled back? This goes into the audit trail.",
    );
    if (!reason?.trim()) return;
    setBusy(true);
    try {
      await rollback([...selected], reason.trim());
      setSelected(new Set());
    } finally {
      setBusy(false);
    }
  }

  if (!records.length) {
    return (
      <Panel title="Records">
        <Empty>No records yet. Run a migration first.</Empty>
      </Panel>
    );
  }

  return (
    <Panel
      title={`Records (${records.length})`}
      subtitle={`${pushed.length} in the target system, ${failed.length} retryable`}
      right={
        <div className="flex items-center gap-2">
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="filter…"
            className="w-32 rounded-lg border border-line bg-canvas px-2 py-1 text-[12px] outline-none focus:border-brand"
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
              Retry {failed.length} failed
            </Button>
          )}
          {selected.size > 0 && (
            <Button size="sm" variant="danger" disabled={busy} onClick={doRollback}>
              Roll back {selected.size}
            </Button>
          )}
        </div>
      }
    >
      <div className="max-h-[68vh] overflow-auto">
        <table className="w-full text-[12px]">
          <thead className="sticky top-0 bg-raised">
            <tr className="text-left text-[10px] tracking-wide text-faint uppercase">
              <th className="w-8 px-3 py-2" />
              <th className="px-3 py-2 font-medium">Code</th>
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Department</th>
              <th className="px-3 py-2 font-medium">Joined</th>
              <th className="px-3 py-2 font-medium">Sources</th>
              <th className="px-3 py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((record) => (
              <tr key={record.key} className="border-t border-line/60 hover:bg-raised/40">
                <td className="px-3 py-1.5">
                  {record.push_status === "success" && (
                    <input
                      type="checkbox"
                      checked={selected.has(record.key)}
                      onChange={() => toggle(record.key)}
                      aria-label={`select ${record.key}`}
                    />
                  )}
                </td>
                <td className="mono px-3 py-1.5">{record.fields.employee_code ?? record.key}</td>
                <td className="px-3 py-1.5">
                  {record.fields.first_name} {record.fields.last_name}
                </td>
                <td className="px-3 py-1.5 text-muted">{record.fields.department ?? "—"}</td>
                <td className="mono px-3 py-1.5 text-muted">
                  {record.fields.date_of_joining ?? "—"}
                </td>
                <td className="px-3 py-1.5 text-faint">
                  {record.sources.length > 1 ? `${record.sources.length} files` : "1 file"}
                </td>
                <td className="px-3 py-1.5">
                  <Badge tone={STATUS_TONE[record.push_status] ?? "neutral"}>
                    {record.push_status}
                  </Badge>
                  {record.push_detail && (
                    <span className="ml-1.5 text-[11px] text-faint">{record.push_detail}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
