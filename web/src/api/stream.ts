import type { Escalation, Summary, TargetRecord } from "../types";

export interface StreamHandlers {
  onProgress?: (text: string) => void;
  onAwaiting?: (escalations: Escalation[], summary: Summary, round: number) => void;
  onSummary?: (summary: Summary) => void;
  onDone?: (summary: Summary, records: TargetRecord[]) => void;
  onError?: (message: string) => void;
}

/**
 * Split an SSE byte-stream buffer into complete events.
 *
 * Pulled out as a pure function because it is the one piece of the transport
 * that is genuinely easy to get wrong and impossible to notice: a frame can be
 * split across chunk boundaries, and a naive `split` on each chunk drops the
 * event straddling the seam. Silently — the run just appears to skip a step.
 *
 * Returns the parsed events plus whatever partial text is left over, which the
 * caller carries into the next chunk.
 */
export function drainFrames(buffer: string): { events: any[]; rest: string } {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  const events: any[] = [];

  for (const frame of parts) {
    // An SSE frame may carry comments and other fields; only `data:` matters,
    // and a multi-line data payload is joined per the spec.
    const data = frame
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).replace(/^ /, ""))
      .join("\n");
    if (!data) continue;
    try {
      events.push(JSON.parse(data));
    } catch {
      // A malformed frame is skipped, never thrown: one bad event must not
      // take down a stream that is still reporting a live migration.
    }
  }
  return { events, rest };
}

/** Route one parsed event to its handler. Unknown types are ignored so the
 *  server can add event types without breaking an older page. */
export function dispatch(event: any, handlers: StreamHandlers): void {
  switch (event?.type) {
    case "progress":
      handlers.onProgress?.(event.text);
      break;
    case "summary":
    case "escalations":
      handlers.onSummary?.(event.summary ?? {});
      break;
    case "awaiting":
      handlers.onAwaiting?.(event.escalations ?? [], event.summary ?? {}, Number(event.round ?? 1));
      break;
    case "done":
      handlers.onDone?.(event.summary ?? {}, event.records ?? []);
      break;
    case "error":
      handlers.onError?.(event.message ?? "something went wrong");
      break;
    default:
      break;
  }
}

/**
 * Read a run's event stream.
 *
 * `fetch` + ReadableStream rather than EventSource, for two reasons: the
 * connection can be aborted cleanly when the view unmounts or the run is
 * restarted, and partial frames can be buffered properly across chunks.
 */
export async function streamRun(
  runId: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api/runs/${runId}/events`, { signal });
  if (!response.body) throw new Error("this browser cannot stream the response");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { events, rest } = drainFrames(buffer);
    buffer = rest;
    for (const event of events) dispatch(event, handlers);
  }
}
