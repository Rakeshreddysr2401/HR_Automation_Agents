import { beforeEach, describe, expect, it } from "vitest";
import { apply, resolveTheme, useTheme } from "./themeStore";

/** Appearance has to survive a browser that refuses to store anything — a
 *  private window should still render, just without remembering the choice. */
describe("themeStore", () => {
  beforeEach(() => {
    localStorage.clear();
    useTheme.setState({ theme: "system", accent: "indigo", density: "comfortable" });
  });

  it("stamps all three axes onto the document element", () => {
    apply({ theme: "dark", accent: "violet", density: "compact" });
    const root = document.documentElement;
    expect(root.getAttribute("data-theme")).toBe("dark");
    expect(root.getAttribute("data-accent")).toBe("violet");
    expect(root.getAttribute("data-density")).toBe("compact");
  });

  it("resolves an explicit choice without consulting the system", () => {
    expect(resolveTheme("dark")).toBe("dark");
    expect(resolveTheme("light")).toBe("light");
  });

  it("resolves 'system' to a concrete theme", () => {
    expect(["light", "dark"]).toContain(resolveTheme("system"));
  });

  it("persists a chosen theme and reflects it in `effective`", () => {
    useTheme.getState().setTheme("dark");
    expect(useTheme.getState().theme).toBe("dark");
    expect(useTheme.getState().effective).toBe("dark");
    expect(JSON.parse(localStorage.getItem("hrm.appearance")!).theme).toBe("dark");
  });

  it("cycles light -> dark -> system", () => {
    useTheme.getState().setTheme("light");
    useTheme.getState().cycleTheme();
    expect(useTheme.getState().theme).toBe("dark");
    useTheme.getState().cycleTheme();
    expect(useTheme.getState().theme).toBe("system");
    useTheme.getState().cycleTheme();
    expect(useTheme.getState().theme).toBe("light");
  });

  it("toggles density both ways", () => {
    useTheme.getState().toggleDensity();
    expect(useTheme.getState().density).toBe("compact");
    useTheme.getState().toggleDensity();
    expect(useTheme.getState().density).toBe("comfortable");
  });

  it("changes the accent without disturbing the theme", () => {
    useTheme.getState().setTheme("dark");
    useTheme.getState().setAccent("emerald");
    expect(useTheme.getState().accent).toBe("emerald");
    expect(useTheme.getState().theme).toBe("dark");
    expect(document.documentElement.getAttribute("data-accent")).toBe("emerald");
  });
});
