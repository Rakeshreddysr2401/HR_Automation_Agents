import { create } from "zustand";
import { api, streamRun } from "../api/client";
import type { AuditEntry, Decision, Escalation, ModelStatus, Summary, TargetRecord } from "../types";

export type Tab = "run" | "queue" | "decisions" | "records" | "audit";

interface Activity {
  text: string;
  at: number;
}

interface State {
  runId: string | null;
  status: "idle" | "running" | "awaiting" | "complete" | "error";
  tab: Tab;
  activity: Activity[];
  escalations: Escalation[];
  records: TargetRecord[];
  audit: AuditEntry[];
  summary: Summary;
  models: ModelStatus | null;
  error: string | null;
  /** Answers staged in the UI but not yet sent, keyed by escalation subject. */
  draft: Record<string, Decision>;
  submitting: boolean;
  focused: number;

  setTab: (tab: Tab) => void;
  setFocused: (index: number) => void;
  stage: (subject: string, answer: Decision) => void;
  unstage: (subject: string) => void;
  loadHealth: () => Promise<void>;
  start: (files: File[]) => Promise<void>;
  submit: () => Promise<void>;
  refresh: () => Promise<void>;
  retry: (keys?: string[]) => Promise<void>;
  rollback: (keys: string[], reason: string) => Promise<void>;
}

let controller: AbortController | null = null;

export const useStore = create<State>((set, get) => ({
  runId: null,
  status: "idle",
  tab: "run",
  activity: [],
  escalations: [],
  records: [],
  audit: [],
  summary: {},
  models: null,
  error: null,
  draft: {},
  submitting: false,
  focused: 0,

  setTab: (tab) => set({ tab }),
  setFocused: (focused) => set({ focused }),
  stage: (subject, answer) => set((s) => ({ draft: { ...s.draft, [subject]: answer } })),
  unstage: (subject) =>
    set((s) => {
      const draft = { ...s.draft };
      delete draft[subject];
      return { draft };
    }),

  loadHealth: async () => {
    try {
      const { models } = await api.health();
      set({ models });
    } catch {
      set({ models: null });
    }
  },

  start: async (files) => {
    controller?.abort();
    controller = new AbortController();
    set({
      status: "running",
      activity: [],
      escalations: [],
      records: [],
      audit: [],
      summary: {},
      draft: {},
      error: null,
      tab: "run",
      focused: 0,
    });
    try {
      const { run_id } = await api.createRun(files);
      set({ runId: run_id });
      await consume(run_id, set, get, controller.signal);
    } catch (error) {
      set({ status: "error", error: (error as Error).message });
    }
  },

  submit: async () => {
    const { runId, draft } = get();
    if (!runId || Object.keys(draft).length === 0) return;
    set({ submitting: true });
    try {
      await api.submitDecisions(runId, expand(draft));
      set({ submitting: false, draft: {}, status: "running", tab: "run", focused: 0 });
      controller?.abort();
      controller = new AbortController();
      await consume(runId, set, get, controller.signal);
    } catch (error) {
      set({ submitting: false, status: "error", error: (error as Error).message });
    }
  },

  refresh: async () => {
    const { runId } = get();
    if (!runId) return;
    const [records, audit] = await Promise.all([api.records(runId), api.audit(runId)]);
    set({ records: records.records, audit: audit.audit });
  },

  retry: async (keys) => {
    const { runId } = get();
    if (!runId) return;
    await api.retry(runId, keys);
    await get().refresh();
  },

  rollback: async (keys, reason) => {
    const { runId } = get();
    if (!runId) return;
    await api.rollback(runId, keys, reason);
    await get().refresh();
  },
}));

/**
 * Some answers imply a second key the backend reads separately - clearing one
 * manager to break a reporting cycle, for instance, is recorded both as the
 * answer to the cycle question and as the instruction that acts on it.
 */
function expand(draft: Record<string, Decision>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [subject, answer] of Object.entries(draft)) {
    out[subject] = answer;
    if (typeof answer === "string" && answer.startsWith("cycle-clear:")) {
      out[answer] = true;
    }
  }
  return out;
}

async function consume(
  runId: string,
  set: (partial: Partial<State>) => void,
  get: () => State,
  signal: AbortSignal,
) {
  try {
    await streamRun(
      runId,
      {
        onProgress: (text) =>
          set({ activity: [...get().activity, { text, at: Date.now() }] }),
        onSummary: (summary) => set({ summary: { ...get().summary, ...summary } }),
        onAwaiting: (escalations, summary) => {
          set({
            escalations,
            summary: { ...get().summary, ...summary },
            status: "awaiting",
            tab: escalations.length ? "queue" : get().tab,
            focused: 0,
          });
          void get().refresh();
        },
        onDone: (summary, records) => {
          set({
            status: "complete",
            summary: { ...get().summary, ...summary },
            records,
            escalations: [],
          });
          void get().refresh();
        },
        onError: (message) => set({ status: "error", error: message }),
      },
      signal,
    );
  } catch (error) {
    if ((error as Error).name !== "AbortError") {
      set({ status: "error", error: (error as Error).message });
    }
  }
}
