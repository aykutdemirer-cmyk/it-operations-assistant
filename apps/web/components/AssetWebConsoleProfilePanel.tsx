"use client";

import { useEffect, useState } from "react";

import {
  deleteWebConsoleProfile,
  fetchWebConsoleProfile,
  saveWebConsoleProfile,
  type WebConsoleProfile,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AssetSnmpPanel.module.css";

type FetchStatus = "loading" | "done" | "error";

type FormState = {
  port: string;
  verify_ssl: boolean;
  login_path: string;
  username_field: string;
  password_field: string;
};

const DEFAULT_FORM: FormState = {
  port: "443",
  verify_ssl: false,
  login_path: "/login",
  username_field: "username",
  password_field: "password",
};

/** Faz 76 — PAM Web Konsolu profili: giriş formunun GERÇEK alan
 * adlarını (yalnızca `PAM_ADMIN`) yapılandırır. Kod içine sabit bir
 * Firewalla şeması UYDURULMADI — Admin gerçek cihaza bakıp girer (bkz.
 * docs/roadmap.md Faz 76). Görüntüleme yetkisi olmayan kullanıcılar
 * bu sekmeyi zaten görmez (buton `AssetDetails.tsx`'te aynı cihaz
 * tipi koşuluyla açılır); yapılandırma formu ayrıca `PAM_ADMIN`
 * gerektirir. */
export function AssetWebConsoleProfilePanel({ assetId }: { assetId: string }) {
  const { token, currentUser } = useAuth();
  const { t } = useLocale();
  const d = t.assetDetails.webConsole;
  const canManage = currentUser?.permissions.includes("PAM_ADMIN") ?? false;

  const [status, setStatus] = useState<FetchStatus>("loading");
  const [profile, setProfile] = useState<WebConsoleProfile | null>(null);
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  function load() {
    if (!token) return;
    fetchWebConsoleProfile(token, assetId)
      .then((data) => {
        setProfile(data);
        if (data) {
          setForm({
            port: String(data.port),
            verify_ssl: data.verify_ssl,
            login_path: data.login_path,
            username_field: data.username_field,
            password_field: data.password_field,
          });
        }
        setStatus("done");
      })
      .catch(() => setStatus("error"));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, assetId]);

  async function handleSave() {
    if (!token) return;
    setSaving(true);
    setErrorMessage(null);
    try {
      const saved = await saveWebConsoleProfile(token, assetId, {
        port: Number(form.port),
        verify_ssl: form.verify_ssl,
        login_path: form.login_path.trim(),
        username_field: form.username_field.trim(),
        password_field: form.password_field.trim(),
      });
      setProfile(saved);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : d.saveError);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!token) return;
    setSaving(true);
    try {
      await deleteWebConsoleProfile(token, assetId);
      setProfile(null);
      setForm(DEFAULT_FORM);
    } finally {
      setSaving(false);
    }
  }

  if (status === "loading") return <p className={styles.hint}>{t.common.loading}</p>;
  if (status === "error") return <p className={styles.warning}>{d.loadError}</p>;

  if (!canManage) {
    return <p className={styles.hint}>{profile ? d.configuredReadOnly : d.notConfiguredNoAccess}</p>;
  }

  return (
    <div className={styles.wrap}>
      <p className={styles.hint}>{d.description}</p>
      {!profile && <p className={styles.warning}>{d.notConfigured}</p>}

      <div className={styles.configurePanel}>
        <label className={styles.field}>
          <span>{d.fields.loginPath}</span>
          <input type="text" value={form.login_path} onChange={(e) => setForm({ ...form, login_path: e.target.value })} />
        </label>
        <label className={styles.field}>
          <span>{d.fields.usernameField}</span>
          <input
            type="text"
            value={form.username_field}
            onChange={(e) => setForm({ ...form, username_field: e.target.value })}
          />
        </label>
        <label className={styles.field}>
          <span>{d.fields.passwordField}</span>
          <input
            type="text"
            value={form.password_field}
            onChange={(e) => setForm({ ...form, password_field: e.target.value })}
          />
        </label>
        <label className={styles.field}>
          <span>{d.fields.port}</span>
          <input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} />
        </label>
        <label className={styles.field}>
          <span>
            <input
              type="checkbox"
              checked={form.verify_ssl}
              onChange={(e) => setForm({ ...form, verify_ssl: e.target.checked })}
            />{" "}
            {d.fields.verifySsl}
          </span>
        </label>

        {errorMessage && <p className={styles.warning}>{errorMessage}</p>}

        <div className={styles.actions}>
          <button type="button" className={styles.primaryButton} onClick={handleSave} disabled={saving}>
            {saving ? t.common.loading : d.save}
          </button>
          {profile && (
            <button type="button" className={styles.linkButtonDanger} onClick={handleDelete} disabled={saving}>
              {d.delete}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
