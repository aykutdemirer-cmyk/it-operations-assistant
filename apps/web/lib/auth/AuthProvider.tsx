"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { fetchMe, loginRequest, type CurrentUser } from "@/lib/api";

// Test dosyalarının (bkz. `tests/pages.test.tsx`) gerçek anahtarı
// `localStorage`'a yazıp bir kullanıcı oturumunu simüle edebilmesi için
// dışa açıldı — üretim kodunda bu sabite doğrudan erişim gerekmez.
export const TOKEN_STORAGE_KEY = "itops-auth-token";

// JWT `localStorage`'da tutuluyor — `theme`/`locale` ile AYNI, bu
// kod tabanında zaten kurulu desen (bkz. `lib/theme/ThemeProvider.tsx`).
// BİLİNÇLİ bir ödünleşim: `localStorage` bir XSS'e karşı `httpOnly`
// cookie kadar korumalı DEĞİL, ama bu proje şu an server-side session/
// cookie altyapısı KURMUYOR (frontend backend'e yalnızca REST üzerinden
// konuşur, ayrı bir Next.js backend-for-frontend katmanı yok) — token
// kısa ömürlü (`JWT_TOKEN_TTL_MINUTES`, varsayılan 8 saat) ve yalnızca
// kimlik doğrular, hiçbir kimlik bilgisi DEĞERİ taşımaz.
type AuthContextValue = {
  token: string | null;
  currentUser: CurrentUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // setState çağrıları bir microtask'a ertelendi — bkz. `lib/i18n/
    // LocaleProvider.tsx`'teki aynı desen (react-hooks/set-state-in-effect).
    const stored = getStoredToken();
    if (!stored) {
      Promise.resolve().then(() => setLoading(false));
      return;
    }
    Promise.resolve().then(() => setToken(stored));
    fetchMe(stored)
      .then((user) => setCurrentUser(user))
      .catch(() => {
        // Token geçersiz/süresi dolmuş — sessizce temizle, kullanıcıyı
        // tekrar giriş yapmaya zorla.
        try {
          window.localStorage.removeItem(TOKEN_STORAGE_KEY);
        } catch {
          // yoksay
        }
        setToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  async function login(username: string, password: string) {
    const response = await loginRequest(username, password);
    try {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, response.access_token);
    } catch {
      // yoksay — token yine de bellekte (state) tutulur
    }
    setToken(response.access_token);
    setCurrentUser(response.user);
  }

  function logout() {
    try {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    } catch {
      // yoksay
    }
    setToken(null);
    setCurrentUser(null);
  }

  return (
    <AuthContext.Provider value={{ token, currentUser, loading, login, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth, AuthProvider içinde kullanılmalı");
  }
  return ctx;
}
