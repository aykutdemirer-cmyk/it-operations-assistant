import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

import "@testing-library/jest-dom/vitest";

// jsdom, açık bir origin (`url`) yapılandırılmadığında localStorage'ı
// "opaque origin" sayıp tamamen devre dışı bırakıyor (jsdom 27+).
// `vitest.config.mts`'teki `environmentOptions` bunu düzeltmeyi
// denedi ama güvenilir değildi — burada basit, bellek içi bir
// polyfill ile garanti altına alınıyor (yalnızca gerçekten
// çalışmıyorsa devreye girer).
function ensureLocalStorage() {
  try {
    window.localStorage.setItem("__itops_probe__", "1");
    window.localStorage.removeItem("__itops_probe__");
    return;
  } catch {
    // aşağıda polyfill ile devam
  }

  const store = new Map<string, string>();
  const polyfill: Storage = {
    getItem: (key) => (store.has(key) ? store.get(key)! : null),
    setItem: (key, value) => {
      store.set(key, String(value));
    },
    removeItem: (key) => {
      store.delete(key);
    },
    clear: () => {
      store.clear();
    },
    key: (index) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size;
    },
  };

  Object.defineProperty(window, "localStorage", {
    value: polyfill,
    writable: true,
    configurable: true,
  });
}

ensureLocalStorage();

afterEach(() => {
  cleanup();
});
