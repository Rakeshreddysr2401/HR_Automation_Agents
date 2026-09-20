import "@testing-library/react";

/**
 * Node 25 ships an experimental global `localStorage` that shadows jsdom's and
 * is missing part of the Storage interface (`clear`, notably) — so without
 * this, the appearance tests exercise Node's object rather than the one a
 * browser would hand them. Install a clean in-memory Storage instead, which is
 * both deterministic and actually the shape the app sees in a browser.
 */
function memoryStorage(): Storage {
  let map = new Map<string, string>();
  return {
    get length() {
      return map.size;
    },
    clear: () => {
      map = new Map();
    },
    getItem: (key: string) => map.get(key) ?? null,
    key: (index: number) => [...map.keys()][index] ?? null,
    removeItem: (key: string) => {
      map.delete(key);
    },
    setItem: (key: string, value: string) => {
      map.set(key, String(value));
    },
  };
}

Object.defineProperty(globalThis, "localStorage", {
  value: memoryStorage(),
  configurable: true,
  writable: true,
});

/** jsdom has no matchMedia, and the appearance store asks it for the OS theme. */
if (!globalThis.matchMedia) {
  Object.defineProperty(globalThis, "matchMedia", {
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
    configurable: true,
    writable: true,
  });
}
