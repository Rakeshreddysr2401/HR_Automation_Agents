import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // The CSS pipeline is Tailwind + a token layer that only means anything in
    // a browser, and none of these tests assert on computed styles.
    css: false,
  },
});
