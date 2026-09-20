import type {
  AuditEntry,
  Escalation,
  Mapping,
  MemoryEntry,
  ModelStatus,
  Plan,
  Policy,
  RunSummaryRow,
  Summary,
  TargetRecord,
  TargetSchema,
} from "../types";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    // FastAPI puts the useful part in `detail`; falling back to raw text keeps
    // a proxy error or an HTML error page readable rather than "[object Object]".
    const body = await response.text();
    let message = body;
    try {
      message = JSON.parse(body).detail ?? body;
    } catch {
      /* not JSON */
    }
    throw new Error(message || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => json<{ status: string; models: ModelStatus }>("/api/health"),

  policy: () => json<Policy>("/api/policy"),

  schema: () => json<TargetSchema>("/api/schema"),

  runs: () => json<{ runs: RunSummaryRow[] }>("/api/runs"),

  createRun: (files: File[]) => {
    if (files.length === 0) {
      return json<{ run_id: string; files: string[] }>("/api/runs", {
        method: "POST",
        body: JSON.stringify({ use_sample: true }),
      });
    }
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    // No Content-Type header: the browser must set the multipart boundary.
    return fetch("/api/runs", { method: "POST", body: form }).then(async (r) => {
      if (!r.ok) throw new Error((await r.text()) || `upload failed: ${r.status}`);
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

  mappings: (runId: string) => json<{ mappings: Mapping[] }>(`/api/runs/${runId}/mappings`),

  plan: (runId: string) => json<Plan>(`/api/runs/${runId}/plan`),

  recipe: (runId: string) => json<Record<string, any>>(`/api/runs/${runId}/recipe`),

  /** The YAML rendering, as text — what the download button saves. */
  recipeYaml: (runId: string) =>
    fetch(`/api/runs/${runId}/recipe?format=yaml`).then((r) => {
      if (!r.ok) throw new Error(`could not export: ${r.status}`);
      return r.text();
    }),

  applyRecipe: (runId: string, recipe: string) =>
    json<{ seeded: number; subjects: string[] }>(`/api/runs/${runId}/recipe`, {
      method: "POST",
      body: JSON.stringify({ recipe }),
    }),

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
    json<{ rolled_back: string[]; count: number; failed?: string[] }>(`/api/runs/${runId}/rollback`, {
      method: "POST",
      body: JSON.stringify({ keys, reason }),
    }),

  memory: () => json<{ memory: MemoryEntry[] }>("/api/memory"),
};

export { streamRun, drainFrames, dispatch } from "./stream";
export type { StreamHandlers } from "./stream";
