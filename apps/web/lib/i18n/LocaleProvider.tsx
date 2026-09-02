"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { translations, type Locale } from "./translations";

const STORAGE_KEY = "itops-locale";
const DEFAULT_LOCALE: Locale = "tr";

type LocaleContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (typeof translations)[Locale];
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

/**
 * Dil sistemi — sunucu ve ilk client render'ı her zaman `tr` (varsayılan)
 * ile eşleşir; kalıcı seçim `localStorage`'dan yalnızca mount sonrası
 * bir `useEffect`'te okunur. Bu, hydration mismatch riskini ortadan
 * kaldırır (sunucu çıktısı ile ilk client render'ı asla farklı olmaz);
 * bedeli, kullanıcı daha önce "en" seçmişse bir sonraki ziyarette çok
 * kısa bir "tr" karesi görünmesidir — kabul edilebilir bir ödünleşim.
 */
export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);

  useEffect(() => {
    // setState çağrısı bilerek bir microtask'a ertelendi — effect
    // gövdesinde senkron setState react-hooks/set-state-in-effect
    // tarafından reddediliyor (bkz. NetworkTopology.tsx'teki aynı
    // desen).
    Promise.resolve().then(() => {
      try {
        const stored = window.localStorage.getItem(STORAGE_KEY);
        if (stored === "tr" || stored === "en") {
          setLocaleState(stored);
          document.documentElement.lang = stored;
        }
      } catch {
        // localStorage erişilemiyor olabilir (gizli mod vb.) — varsayılanla devam.
      }
    });
  }, []);

  function setLocale(next: Locale) {
    setLocaleState(next);
    document.documentElement.lang = next;
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // yazılamazsa yalnızca bu oturum için geçerli kalır.
    }
  }

  return (
    <LocaleContext.Provider value={{ locale, setLocale, t: translations[locale] }}>
      {children}
    </LocaleContext.Provider>
  );
}

export function useLocale(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) {
    throw new Error("useLocale must be used within a LocaleProvider");
  }
  return ctx;
}
