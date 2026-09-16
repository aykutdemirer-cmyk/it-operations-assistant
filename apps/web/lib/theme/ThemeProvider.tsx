"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

// Faz 59 — Faz 21'in `"dark" | "light"` ikilisi 4 temalı bir motora
// genişletildi. `fortios-dark` bugünkü koyu paletle BİREBİR aynıdır
// (varsayılan), `enterprise-light` bugünkü açık palettir.
export type Theme = "fortios-dark" | "cyber-neon" | "midnight-blue" | "enterprise-light";

export const ALL_THEMES: Theme[] = ["fortios-dark", "cyber-neon", "midnight-blue", "enterprise-light"];

const STORAGE_KEY = "itops-theme";
const DEFAULT_THEME: Theme = "fortios-dark";

// Faz 21'de saklanmış eski değerlerin karşılığı — mevcut kullanıcıların
// seçimi kaybolmasın / dark mode kırılmasın diye migrate edilir.
const LEGACY_MAP: Record<string, Theme> = {
  dark: "fortios-dark",
  light: "enterprise-light",
};

type ThemeContextValue = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function normalizeStored(value: string | null): Theme | null {
  if (!value) return null;
  if ((ALL_THEMES as string[]).includes(value)) return value as Theme;
  return LEGACY_MAP[value] ?? null;
}

/**
 * Tema sistemi — `LocaleProvider` ile aynı desen: sunucu ve ilk client
 * render'ı her zaman `fortios-dark` (mevcut varsayılan görünüm) ile
 * eşleşir; kalıcı seçim yalnızca mount sonrası okunur/uygulanır.
 * `globals.css` `:root[data-theme="<tema>"]` seçicileriyle açık seçimi
 * `prefers-color-scheme`'in önüne geçirir.
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

    const normalized = normalizeStored(stored);
    if (normalized) {
      document.documentElement.dataset.theme = normalized;
      // Eski değerse kalıcı olarak da güncelle (bir kereye mahsus migrasyon).
      if (normalized !== stored) {
        try {
          window.localStorage.setItem(STORAGE_KEY, normalized);
        } catch {
          // yazılamazsa sorun değil, bir sonraki `setTheme` düzeltir.
        }
      }
      Promise.resolve().then(() => setThemeState(normalized));
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
