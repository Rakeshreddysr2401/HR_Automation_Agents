import { create } from "zustand";
import { api, streamRun } from "../api/client";
import type {
  AuditEntry,
  Decision,
  Escalation,
  Mapping,
  ModelStatus,
  Plan,
  Policy,
  RunSummaryRow,
  Summary,
  TargetRecord,
  TargetSchema,
} from "../types";

export type Tab = "run" | "queue" | "mapping" | "plan" | "records" | "decisions" | "audit" | "policy";

export interface Activity {
  text: string;
  at: number;
}

export interface Toast {
  id: number;
  tone: "auto" | "ask" | "brand";
  text: string;
}

interface State {
  runId: string | null;
  status: "idle" | "running" | "awaiting" | "complete" | "error";
  tab: Tab;
  activity: Activity[];
  escalations: Escalation[];
  records: TargetRecord[];
  audit: AuditEntry[];
  mappings: Mapping[];
  plan: Plan | null;
  policy: Policy | null;
  schema: TargetSchema | null;
  history: RunSummaryRow[];
  summary: Summary;
  models: ModelStatus | null;
  error: string | null;
  toasts: Toast[];
  /** Answers staged in the UI but not yet sent, keyed by escalation subject. */
  draft: Record<string, Decision>;
  submitting: boolean;
  focused: number;
  /** Which analysis pass the open questions came from; 1 on a fresh run. */
  round: number;
  paletteOpen: boolean;
  helpOpen: boolean;

  setTab: (tab: Tab) => void;
  setFocused: (index: number) => void;
  setPalette: (open: boolean) => void;
  setHelp: (open: boolean) => void;
  stage: (subject: string, answer: Decision) => void;
  unstage: (subject: string) => void;
  toast: (tone: Toast["tone"], text: string) => void;
  dismissToast: (id: number) => void;
  loadHealth: () => Promise<void>;
  loadReference: () => Promise<void>;
  loadHistory: () => Promise<void>;
  openRun: (runId: string) => Promise<void>;
  start: (files: File[], recipe?: string) => Promise<void>;
  submit: () => Promise<void>;
  refresh: () => Promise<void>;
  loadPlan: () => Promise<void>;
  retry: (keys?: string[]) => Promise<void>;
  rollback: (keys: string[], reason: string) => Promise<void>;
}

let controller: AbortController | null = null;
let toastSeq = 0;

export const useStore = create<State>((set, get) => ({
  runId: null,
  status: "idle",
  tab: "run",
  activity: [],
  escalations: [],
  records: [],
  audit: [],
  mappings: [],
  plan: null,
  policy: null,
  schema: null,
  history: [],
  summary: {},
  models: null,
  error: null,
  toasts: [],
  draft: {},
  submitting: false,
  focused: 0,
  round: 1,
  paletteOpen: false,
  helpOpen: false,

  setTab: (tab) => set({ tab }),
  setFocused: (focused) => set({ focused }),
  setPalette: (paletteOpen) => set({ paletteOpen }),
  setHelp: (helpOpen) => set({ helpOpen }),
  stage: (subject, answer) => set((s) => ({ draft: { ...s.draft, [subject]: answer } })),
  unstage: (subject) =>
    set((s) => {
      const draft = { ...s.draft };
      delete draft[subject];
      return { draft };
    }),

  toast: (tone, text) => {
    const id = ++toastSeq;
    set((s) => ({ toasts: [...s.toasts, { id, tone, text }] }));
    setTimeout(() => get().dismissToast(id), 4200);
  },
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  loadHealth: async () => {
    try {
      const { models } = await api.health();
      set({ models });
    } catch {
      set({ models: null });
    }
  },

  /** Policy and schema don't change between runs, so they load once at boot. */
  loadReference: async () => {
    const [policy, schema] = await Promise.allSettled([api.policy(), api.schema()]);
    set({
      policy: policy.status === "fulfilled" ? policy.value : null,
      schema: schema.status === "fulfilled" ? schema.value : null,
    });
  },

  loadHistory: async () => {
    try {
      const { runs } = await api.runs();
      set({ history: runs });
    } catch {
      set({ history: [] });
    }
  },

  /** Reopen a finished run from history, read-only — no stream is started. */
  openRun: async (runId) => {
    controller?.abort();
    set({ runId, activity: [], draft: {}, error: null, focused: 0, plan: null });
    try {
      const [summary, escalations] = await Promise.all([
        api.summary(runId),
        api.escalations(runId),
      ]);
      set({
        summary: summary.summary ?? {},
        escalations: escalations.escalations.filter((e) => e.status === "open"),
        status: summary.status === "complete" ? "complete" : "awaiting",
        tab: "records",
      });
      await get().refresh();
      get().toast("brand", `Opened ${runId}`);
    } catch (error) {
      set({ error: (error as Error).message });
    }
  },

  start: async (files, recipe) => {
    controller?.abort();
    controller = new AbortController();
    set({
      status: "running",
      activity: [],
      escalations: [],
      records: [],
      audit: [],
      mappings: [],
      plan: null,
      summary: {},
      draft: {},
      error: null,
      tab: "run",
      focused: 0,
      round: 1,
    });
    try {
      const { run_id } = await api.createRun(files);
      set({ runId: run_id });
      if (recipe?.trim()) {
        const { seeded } = await api.applyRecipe(run_id, recipe);
        get().toast("brand", `Replayed ${seeded} answer(s) from the recipe`);
      }
      await consume(run_id, set, get, controller.signal);
      void get().loadHistory();
    } catch (error) {
      set({ status: "error", error: (error as Error).message });
    }
  },

  submit: async () => {
    const { runId, draft } = get();
    if (!runId || Object.keys(draft).length === 0) return;
    const count = Object.keys(draft).length;
    set({ submitting: true });
    try {
      await api.submitDecisions(runId, expand(draft));
      // The plan is a snapshot of one analysis pass; the answers just sent
      // will change it, so drop it rather than show the previous pass's payloads.
      set({ submitting: false, draft: {}, status: "running", tab: "run", focused: 0, plan: null });
      get().toast("auto", `${count} decision(s) applied — re-running`);
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
    const [records, audit, mappings] = await Promise.allSettled([
      api.records(runId),
      api.audit(runId),
      api.mappings(runId),
    ]);
    set({
      records: records.status === "fulfilled" ? records.value.records : [],
      audit: audit.status === "fulfilled" ? audit.value.audit : [],
      mappings: mappings.status === "fulfilled" ? mappings.value.mappings : [],
    });
  },

  loadPlan: async () => {
    const { runId } = get();
    if (!runId) return;
    try {
      set({ plan: await api.plan(runId) });
    } catch (error) {
      set({ error: (error as Error).message });
    }
  },

  retry: async (keys) => {
    const { runId } = get();
    if (!runId) return;
    const result = await api.retry(runId, keys);
    await get().refresh();
    const pushed = Number(result.pushed ?? 0);
    const retried = Number(result.retried ?? 0);
    get().toast(
      retried ? "brand" : "ask",
      retried ? `Retried ${retried}: ${pushed} loaded` : "Nothing to retry",
    );
  },

  rollback: async (keys, reason) => {
    const { runId } = get();
    if (!runId) return;
    const result = await api.rollback(runId, keys, reason);
    await get().refresh();
    const failed = result.failed?.length ?? 0;
    get().toast(
      "ask",
      failed
        ? `Rolled back ${result.count}, ${failed} could not be removed from the target`
        : `Rolled back ${result.count} record(s)`,
    );
  },
}));

/**
 * Some answers imply a second key the backend reads separately — clearing one
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
        onProgress: (text) => set({ activity: [...get().activity, { text, at: Date.now() }] }),
        onSummary: (summary) => set({ summary: { ...get().summary, ...summary } }),
        onAwaiting: (escalations, summary, round) => {
          set({
            escalations,
            summary: { ...get().summary, ...summary },
            status: "awaiting",
            tab: escalations.length ? "queue" : get().tab,
            focused: 0,
            round: round || 1,
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
          get().toast("auto", "Migration complete");
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
