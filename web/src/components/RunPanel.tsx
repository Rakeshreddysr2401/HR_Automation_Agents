import { useEffect, useRef, useState } from "react";
import { useStore } from "../state/store";
import { Button, Empty, Panel } from "./ui";

export function RunPanel() {
  const { status, activity, start, summary } = useStore();
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [activity.length]);

  const busy = status === "running";

  return (
    <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
      <Panel title="Source files" subtitle="CSV or Excel exports of the same entity">
        <div className="space-y-3 p-4">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              setFiles(Array.from(e.dataTransfer.files));
            }}
            className={`rounded-xl border-2 border-dashed px-4 py-6 text-center transition
              ${dragging ? "border-brand bg-brand-soft" : "border-line"}`}
          >
            <p className="text-[13px] text-muted">Drop exports here</p>
            <label className="mt-2 inline-block cursor-pointer text-[12px] text-brand underline">
              or choose files
              <input
                type="file"
                multiple
                accept=".csv,.xlsx,.xls"
                className="hidden"
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              />
            </label>
          </div>

          {files.length > 0 && (
            <ul className="space-y-1">
              {files.map((file) => (
                <li key={file.name} className="flex items-center justify-between text-[12px]">
                  <span className="truncate">{file.name}</span>
                  <span className="text-faint">{(file.size / 1024).toFixed(0)} KB</span>
                </li>
              ))}
            </ul>
          )}

          <Button variant="primary" onClick={() => start(files)} disabled={busy}>
            {busy ? "Working…" : files.length ? `Migrate ${files.length} file(s)` : "Run the sample migration"}
          </Button>
          {files.length === 0 && (
            <p className="text-[11px] text-faint">
              With nothing chosen it runs the two bundled exports: a legacy HRIS dump and a
              payroll spreadsheet that disagree with each other in every way that matters.
            </p>
          )}
        </div>
      </Panel>

      <Panel
        title="What the agent is doing"
        subtitle={
          summary.elapsed_seconds ? `last pass took ${summary.elapsed_seconds}s` : undefined
        }
        right={
          busy ? (
            <span className="flex items-center gap-1.5 text-[11px] text-brand">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand" />
              running
            </span>
          ) : undefined
        }
      >
        <div ref={logRef} className="max-h-[62vh] min-h-[220px] overflow-y-auto px-4 py-3">
          {activity.length === 0 ? (
            <Empty>Start a run and its reasoning appears here, line by line.</Empty>
          ) : (
            <ol className="space-y-1.5">
              {activity.map((line, index) => (
                <li key={index} className="animate-in flex gap-2.5 text-[12px] leading-relaxed">
                  <span className="mono mt-0.5 shrink-0 text-[10px] text-faint">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className={line.text.includes("asking") ? "text-ask" : "text-muted"}>
                    {line.text}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </Panel>
    </div>
  );
}
