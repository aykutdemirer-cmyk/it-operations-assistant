"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type Theme = "dark" | "light";

const STORAGE_KEY = "itops-theme";
const DEFAULT_THEME: Theme = "dark";

type ThemeContextValue = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

/**
 * Tema sistemi — `LocaleProvider` ile aynı desen: sunucu ve ilk client
 * render'ı her zaman `dark` (mevcut varsayılan görünüm) ile eşleşir;
 * kalıcı seçim yalnızca mount sonrası okunur/uygulanır. `globals.css`
 * `:root[data-theme="light"]` ve `:root[data-theme="dark"]` seçicileri
 * ile açık seçimi `prefers-color-scheme`'in önüne geçirir; hiçbir seçim
 * yapılmamışsa (bu provider'ın hiç mount olmadığı bir durum pratikte
 * yok, ama ilkeyi korumak için) mevcut medya sorgusu davranışı geçerli
 * kalır.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(DEFAULT_THEME);

  useEffect(() => {
    // setState çağrısı bilerek bir microtask'a ertelendi (bkz.
    // LocaleProvider'daki aynı desen) — DOM yazımı senkron kalabilir,
    // o bir setState değil.
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem(STORAGE_KEY);
    } catch {
      stored = null;
    }

    if (stored === "dark" || stored === "light") {
      document.documentElement.dataset.theme = stored;
      Promise.resolve().then(() => setThemeState(stored as Theme));
    } else {
      document.documentElement.dataset.theme = DEFAULT_THEME;
    }
  }, []);

  function setTheme(next: Theme) {
    setThemeState(next);
    document.documentElement.dataset.theme = next;
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // yazılamazsa yalnızca bu oturum için geçerli kalır.
    }
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return ctx;
}
