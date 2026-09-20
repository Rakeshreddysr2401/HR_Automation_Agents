import { create } from "zustand";

/**
 * Appearance state: the three axes tokens.css exposes.
 *
 * `theme` has three settings but only two values ever reach the DOM — "system"
 * means "follow the OS", and the OS is watched live, so a consultant who flips
 * their laptop to dark at 6pm sees the console follow without a reload.
 */
export type ThemeChoice = "light" | "dark" | "system";
export type Accent = "indigo" | "cyan" | "violet" | "emerald";
export type Density = "comfortable" | "compact";

export const ACCENTS: { id: Accent; label: string }[] = [
  { id: "indigo", label: "Indigo" },
  { id: "cyan", label: "Cyan" },
  { id: "violet", label: "Violet" },
  { id: "emerald", label: "Emerald" },
];

const KEY = "hrm.appearance";

interface Persisted {
  theme: ThemeChoice;
  accent: Accent;
  density: Density;
}

const DEFAULTS: Persisted = { theme: "system", accent: "indigo", density: "comfortable" };

/** localStorage throws in private browsing and is absent under test. Both are
 *  survivable: appearance simply stops persisting, it never breaks the app. */
function read(): Persisted {
  try {
    const raw = globalThis.localStorage?.getItem(KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<Persisted>;
    return {
      theme: parsed.theme ?? DEFAULTS.theme,
      accent: parsed.accent ?? DEFAULTS.accent,
      density: parsed.density ?? DEFAULTS.density,
    };
  } catch {
    return DEFAULTS;
  }
}

function write(value: Persisted) {
  try {
    globalThis.localStorage?.setItem(KEY, JSON.stringify(value));
  } catch {
    // non-persistent session; the choice still applies to this tab
  }
}

function prefersDark(): boolean {
  return globalThis.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export function resolveTheme(choice: ThemeChoice): "light" | "dark" {
  return choice === "system" ? (prefersDark() ? "dark" : "light") : choice;
}

export function apply(value: Persisted) {
  const root = globalThis.document?.documentElement;
  if (!root) return;
  root.setAttribute("data-theme", resolveTheme(value.theme));
  root.setAttribute("data-accent", value.accent);
  root.setAttribute("data-density", value.density);
}

interface ThemeState extends Persisted {
  /** What is actually painted right now, with "system" already resolved. */
  effective: "light" | "dark";
  setTheme: (theme: ThemeChoice) => void;
  setAccent: (accent: Accent) => void;
  setDensity: (density: Density) => void;
  cycleTheme: () => void;
  toggleDensity: () => void;
}

export const useTheme = create<ThemeState>((set, get) => {
  function commit(next: Partial<Persisted>) {
    const { theme, accent, density } = { ...get(), ...next };
    const value = { theme, accent, density };
    write(value);
    apply(value);
    set({ ...value, effective: resolveTheme(theme) });
  }

  const initial = read();
  return {
    ...initial,
    effective: resolveTheme(initial.theme),
    setTheme: (theme) => commit({ theme }),
    setAccent: (accent) => commit({ accent }),
    setDensity: (density) => commit({ density }),
    // light -> dark -> system -> light. Three states, one button.
    cycleTheme: () =>
      commit({
        theme: ({ light: "dark", dark: "system", system: "light" } as const)[get().theme],
      }),
    toggleDensity: () =>
      commit({ density: get().density === "compact" ? "comfortable" : "compact" }),
  };
});

/* Stamp the attributes at module load, before React's first paint, so a
   dark-theme user never sees a white flash. */
apply(read());

/* Follow the OS while the choice is "system". */
globalThis.matchMedia?.("(prefers-color-scheme: dark)").addEventListener?.("change", () => {
  const { theme } = useTheme.getState();
  if (theme !== "system") return;
  apply({ ...useTheme.getState() });
  useTheme.setState({ effective: resolveTheme("system") });
});
