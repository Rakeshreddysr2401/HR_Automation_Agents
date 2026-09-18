import type { AuditEntry, Escalation, ModelStatus, Summary, TargetRecord } from "../types";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => json<{ status: string; models: ModelStatus }>("/api/health"),

  createRun: (files: File[]) => {
    if (files.length === 0) {
      return json<{ run_id: string; files: string[] }>("/api/runs", {
        method: "POST",
        body: JSON.stringify({ use_sample: true }),
      });
    }
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    // Let the browser set the multipart boundary itself.
    return fetch("/api/runs", { method: "POST", body: form }).then((r) => {
      if (!r.ok) throw new Error(`upload failed: ${r.status}`);
      return r.json() as Promise<{ run_id: string; files: string[] }>;
    });
  },

  submitDecisions: (runId: string, decisions: Record<string, unknown>) =>
    json<{ accepted: number }>(`/api/runs/${runId}/decisions`, {
      method: "POST",
      body: JSON.stringify({ decisions }),
    }),

  escalations: (runId: string) =>
    json<{ escalations: Escalation[] }>(`/api/runs/${runId}/escalations`),

  records: (runId: string) => json<{ records: TargetRecord[] }>(`/api/runs/${runId}/records`),

  audit: (runId: string) => json<{ audit: AuditEntry[] }>(`/api/runs/${runId}/audit`),

  summary: (runId: string) =>
    json<{ run_id: string; status: string; files: string[]; summary: Summary | null }>(
      `/api/runs/${runId}/summary`,
    ),

  retry: (runId: string, keys?: string[]) =>
    json<Record<string, unknown>>(`/api/runs/${runId}/retry`, {
      method: "POST",
      body: JSON.stringify({ keys }),
    }),

  rollback: (runId: string, keys: string[], reason: string) =>
    json<{ rolled_back: string[]; count: number }>(`/api/runs/${runId}/rollback`, {
      method: "POST",
      body: JSON.stringify({ keys, reason }),
    }),

  memory: () =>
    json<{ memory: { column_key: string; target: string; times_used: number; updated_at: string }[] }>(
      "/api/memory",
    ),
};

export interface StreamHandlers {
  onProgress?: (text: string) => void;
  onAwaiting?: (escalations: Escalation[], summary: Summary) => void;
  onSummary?: (summary: Summary) => void;
  onDone?: (summary: Summary, records: TargetRecord[]) => void;
  onError?: (message: string) => void;
}

/**
 * Read the run's event stream.
 *
 * Uses fetch with a ReadableStream rather than EventSource so the connection can
 * be aborted cleanly when the view unmounts, and so partial lines are buffered
 * correctly - an SSE frame can be split across chunks, and joining them wrongly
 * silently drops events.
 */
export function streamRun(
  runId: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return fetch(`/api/runs/${runId}/events`, { signal }).then(async (response) => {
    if (!response.body) throw new Error("this browser cannot stream the response");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        const line = frame.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        let event: any;
        try {
          event = JSON.parse(line.slice(6));
        } catch {
          continue; // a malformed frame should never take the stream down
        }
        switch (event.type) {
          case "progress":
            handlers.onProgress?.(event.text);
            break;
          case "summary":
            handlers.onSummary?.(event.summary ?? {});
            break;
          case "escalations":
            handlers.onSummary?.(event.summary ?? {});
            break;
          case "awaiting":
            handlers.onAwaiting?.(event.escalations ?? [], event.summary ?? {});
            break;
          case "done":
            handlers.onDone?.(event.summary ?? {}, event.records ?? []);
            break;
          case "error":
            handlers.onError?.(event.message ?? "something went wrong");
            break;
          default:
            break; // unknown event types are ignored so the API can add more
        }
      }
    }
  });
}
