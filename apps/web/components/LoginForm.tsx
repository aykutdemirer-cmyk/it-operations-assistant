"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./LoginForm.module.css";

/** Faz 46 — `POST /api/auth/login`'e karşı gerçek bir giriş formu.
 * Başarılı girişte `?next=` varsa oraya, yoksa ana sayfaya yönlendirir. */
export function LoginForm() {
  const { t } = useLocale();
  const { login, currentUser } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // GERÇEK bir üretim hatası: `router.replace()` render GÖVDESİNDE
  // çağrılıyordu — React "Cannot update a component (`Router`) while
  // rendering a different component" hatası veriyordu (bir component
  // render OLURKEN başka bir component'i state güncellemesiyle
  // güncellemek YASAK). Yönlendirme bir `useEffect`'e taşındı — yan
  // etkiler render'DAN SONRA çalışmalı, render sırasında DEĞİL.
  useEffect(() => {
    if (currentUser) {
      router.replace(searchParams.get("next") || "/");
    }
  }, [currentUser, router, searchParams]);

  if (currentUser) {
    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(username, password);
      router.replace(searchParams.get("next") || "/");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError(t.auth.loginError);
      } else {
        setError(t.auth.genericError);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.wrap}>
      <form className={styles.card} onSubmit={handleSubmit}>
        <h1 className={styles.title}>{t.auth.loginTitle}</h1>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="login-username">
            {t.auth.username}
          </label>
          <input
            id="login-username"
            className={styles.input}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </div>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="login-password">
            {t.auth.password}
          </label>
          <input
            id="login-password"
            type="password"
            className={styles.input}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        <button type="submit" className={styles.submitButton} disabled={submitting}>
          {submitting ? t.auth.loggingIn : t.auth.loginButton}
        </button>
      </form>
    </div>
  );
}
