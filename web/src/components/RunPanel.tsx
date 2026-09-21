import { useEffect, useRef, useState } from "react";
import { useStore } from "../state/store";
import { Badge, Button, Dot, Empty, Panel, Spinner } from "./ui";
import { IconFile, IconPlay, IconSpark, IconTrash, IconUpload } from "./icons";

export function RunPanel() {
  const { status, activity, start, summary, escalations } = useStore();
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [recipe, setRecipe] = useState("");
  const [showRecipe, setShowRecipe] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [activity.length]);

  const busy = status === "running";

  function accept(list: FileList | null) {
    if (!list) return;
    const allowed = Array.from(list).filter((f) => /\.(csv|xlsx|xls)$/i.test(f.name));
    setFiles(allowed);
  }

  return (
    <div className="grid gap-3 lg:grid-cols-[330px_1fr]">
      <div className="space-y-3">
        <Panel title="Source files" subtitle="Drop the client's CSV or Excel exports here — several files for the same employees is fine" icon={<IconUpload />}>
          <div className="space-y-3">
            <div
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                accept(event.dataTransfer.files);
              }}
              className={`rounded-[var(--radius-lg)] border-2 border-dashed px-4 py-7 text-center transition-colors
                ${dragging ? "border-brand bg-brand-soft" : "border-line hover:border-faint/60"}`}
            >
              <IconUpload className="mx-auto mb-1.5 text-[20px] text-faint" />
              <p className="text-[var(--text-sm)] text-muted">Drop client exports here (.csv, .xlsx)</p>
              <label className="mt-1.5 inline-block cursor-pointer text-[var(--text-sm)] text-brand underline decoration-brand/40 underline-offset-2 hover:decoration-brand">
                or choose files from your computer
                <input
                  type="file"
                  multiple
                  accept=".csv,.xlsx,.xls"
                  className="hidden"
                  onChange={(event) => accept(event.target.files)}
                />
              </label>
            </div>

            {files.length > 0 && (
              <ul className="space-y-1">
                {files.map((file) => (
                  <li
                    key={file.name}
                    className="flex items-center gap-2 rounded-[var(--radius-md)] bg-raised px-2 py-1 text-[var(--text-sm)]"
                  >
                    <IconFile className="shrink-0 text-faint" />
                    <span className="truncate">{file.name}</span>
                    <span className="tnum ml-auto shrink-0 text-[var(--text-xs)] text-faint">
                      {(file.size / 1024).toFixed(0)} KB
                    </span>
                  </li>
                ))}
                <li>
                  <button
                    type="button"
                    onClick={() => setFiles([])}
                    className="flex items-center gap-1 text-[var(--text-xs)] text-faint hover:text-ask"
                  >
                    <IconTrash /> Clear files
                  </button>
                </li>
              </ul>
            )}

            <Button
              variant="primary"
              full
              onClick={() => void start(files, recipe)}
              disabled={busy}
            >
              {busy ? (
                <>
                  <Spinner /> Processing Migration…
                </>
              ) : (
                <>
                  <IconPlay />
                  {files.length ? `Start Migration (${files.length} file${files.length === 1 ? "" : "s"})` : "Run Sample Migration (Demo Dataset)"}
                </>
              )}
            </Button>

            {files.length === 0 && (
              <p className="text-[var(--text-xs)] leading-relaxed text-faint">
                With no file selected, the system runs the demo dataset: a legacy HRIS CSV export and a
                payroll Excel spreadsheet with conflicting headers, ambiguous dates, and rehires.
              </p>
            )}
          </div>
        </Panel>

        {/* Recipe replay. The productisation claim, made operable: paste what a
            previous migration decided and this one starts knowing it. */}
        <Panel
          title="Replay Saved Rules (Recipe)"
          subtitle="Optional — paste a recipe exported from Preview and this run starts already knowing the answers"
          icon={<IconSpark />}
          right={
            <Button size="sm" variant="ghost" onClick={() => setShowRecipe(!showRecipe)}>
              {showRecipe ? "Hide" : "Expand"}
            </Button>
          }
        >
          {showRecipe ? (
            <div className="space-y-2">
              <textarea
                value={recipe}
                onChange={(event) => setRecipe(event.target.value)}
                placeholder={"recipe_version: 1\nanswers:\n  map:payroll_system.xlsx:emp_cd: employee_code"}
                spellCheck={false}
                rows={7}
                className="mono w-full resize-y rounded-[var(--radius-md)] border border-line bg-sunken px-2 py-1.5
                  text-[var(--text-xs)] leading-relaxed outline-none focus:border-brand"
              />
              <p className="text-[var(--text-xs)] leading-relaxed text-faint">
                Only the <code className="mono">answers</code> block is replayed. Column mappings are
                dynamically re-verified against new files to catch unexpected changes.
              </p>
            </div>
          ) : (
            <p className="text-[var(--text-xs)] leading-relaxed text-faint">
              Export a recipe from the Preview tab after completing a migration. Re-running similar
              exports with a recipe runs 100% autonomously without asking repeated questions.
            </p>
          )}
        </Panel>
      </div>

      <Panel
        title="What the agent is doing (live)"
        subtitle={
          summary.elapsed_seconds
            ? `Completed in ${summary.elapsed_seconds}s`
            : "Each line is one decision it made, or one thing it chose to ask you"
        }
        icon={<IconPlay />}
        flush
        right={
          busy ? (
            <span className="flex items-center gap-1.5 text-[var(--text-xs)] text-brand">
              <Dot tone="brand" pulse /> Processing
            </span>
          ) : status === "awaiting" ? (
            <Badge tone="ask">{escalations.length} awaiting review</Badge>
          ) : status === "complete" ? (
            <Badge tone="auto">Completed</Badge>
          ) : undefined
        }
      >
        {/* A sweeping light while the agent works: motion that means "still
            running" without a spinner competing with the log itself. */}
        <div className="h-[2px] w-full overflow-hidden bg-line">
          {busy && <div className="a-sweep h-full w-full" />}
        </div>

        <div ref={logRef} className="max-h-[66vh] min-h-[260px] overflow-y-auto px-[var(--panel-pad)] py-3">
          {activity.length === 0 ? (
            <Empty icon={<IconPlay />}>
              Start a migration to observe live progress here. The agent will show how it
              profiles columns, cleans data, resolves employee identities, and identifies questions
              that need human review.
            </Empty>
          ) : (
            <ol className="space-y-1">
              {activity.map((line, index) => {
                const asking = /asking|ask\b|question|escalat/i.test(line.text);
                const stopping = /stopping early|circuit|breaker/i.test(line.text);
                return (
                  <li
                    key={index}
                    className="a-rise flex gap-2.5 text-[var(--text-sm)] leading-relaxed"
                  >
                    <span className="mono tnum mt-[3px] shrink-0 text-[10px] text-faint">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span
                      className={
                        stopping ? "font-medium text-ask" : asking ? "text-flag" : "text-muted"
                      }
                    >
                      {line.text}
                    </span>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </Panel>
    </div>
  );
}
