"use client";

import { useEffect, useState } from "react";

import {
  fetchVCenterConfig,
  testVCenterConnection,
  updateVCenterConfig,
  type VCenterConfig,
  type VCenterConfigRequest,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { ToastStack, useToasts } from "../Toast";
// LDAP/SMTP yapılandırma merkezleriyle AYNI görsel dil — stiller
// yeniden kullanılıyor (bkz. SmtpConfigurationCenter.tsx docstring'i).
import styles from "../LdapConfigurationCenter.module.css";

type FetchStatus = "loading" | "done" | "error";

type FormState = {
  host: string;
  port: string;
  username: string;
  password: string;
  verify_ssl: boolean;
};

const EMPTY_FORM: FormState = { host: "", port: "443", username: "", password: "", verify_ssl: false };

function configToForm(config: VCenterConfig): FormState {
  return {
    host: config.host,
    port: String(config.port),
    username: config.username,
    // Parola HİÇBİR ZAMAN düz metin dönmez — boş bırakılır.
    password: "",
    verify_ssl: config.verify_ssl,
  };
}

function formToPayload(form: FormState): VCenterConfigRequest {
  return {
    host: form.host.trim(),
    port: Number(form.port),
    username: form.username.trim(),
    password: form.password || null,
    verify_ssl: form.verify_ssl,
  };
}

/** Faz 72 — Ayarlar > "vCenter / vSphere" bölümü. `VCENTER_ADMIN`
 * gerektirir (bkz. `SettingsPanel.tsx::canManageVcenter`). */
export function VCenterConfigPanel() {
  const { token } = useAuth();
  const { t } = useLocale();
  const st = t.settings.vcenterConfig;

  const [config, setConfig] = useState<VCenterConfig | null>(null);
  const [status, setStatus] = useState<FetchStatus>("loading");
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const { toasts, push: pushToast, dismiss: dismissToast } = useToasts();

  function load() {
    if (!token) return;
    fetchVCenterConfig(token)
      .then((data) => {
        setConfig(data);
        setForm(data ? configToForm(data) : EMPTY_FORM);
        setStatus("done");
      })
      .catch(() => setStatus("error"));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function handleSave() {
    if (!token) return;
    setSaving(true);
    setFormError(null);
    try {
      const saved = await updateVCenterConfig(token, formToPayload(form));
      setConfig(saved);
      setForm(configToForm(saved));
      pushToast("success", st.save);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : st.saveError);
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    if (!token) return;
    setTesting(true);
    try {
      const result = await testVCenterConnection(token, formToPayload(form));
      pushToast(result.success ? "success" : "error", `${result.success ? st.testSuccess : st.testError}: ${result.message}`);
      load();
    } catch (err) {
      pushToast("error", err instanceof Error ? err.message : st.testError);
    } finally {
      setTesting(false);
    }
  }

  return (
    <section className={styles.card}>
      <ToastStack toasts={toasts} onDismiss={dismissToast} />
      <div className={styles.header}>
        <h3 className={styles.sectionTitle}>{st.sectionTitle}</h3>
        <p className={styles.description}>{st.description}</p>
      </div>

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {status === "error" && <p className={styles.status}>{st.loadError}</p>}

      {status === "done" && (
        <>
          {config === null && <p className={styles.noData}>{st.notConfigured}</p>}

          {config !== null && (
            <div className={styles.syncSummary}>
              <span className={styles.statusCell}>
                <span
                  className={`${styles.dot} ${
                    config.last_test_status === "success"
                      ? styles.dotReady
                      : config.last_test_status === "error"
                        ? styles.dotDown
                        : styles.dotMuted
                  }`}
                />
                {st.lastTest}: {config.last_test_at ? new Date(config.last_test_at).toLocaleString() : st.lastTestNever}
                {config.last_test_status === "success" && ` — ${st.lastTestStatusSuccess}`}
                {config.last_test_status === "error" && ` — ${st.lastTestStatusError}`}
              </span>
              {config.last_test_status === "error" && config.last_test_error && (
                <span className={styles.formError}>{config.last_test_error}</span>
              )}
            </div>
          )}

          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span>{st.fields.host}</span>
              <input
                type="text"
                value={form.host}
                placeholder={st.fields.hostPlaceholder}
                onChange={(e) => setForm({ ...form, host: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span>{st.fields.port}</span>
              <input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} />
            </label>
            <label className={styles.field}>
              <span>{st.fields.username}</span>
              <input
                type="text"
                value={form.username}
                placeholder={st.fields.usernamePlaceholder}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span>{st.fields.password}</span>
              <input
                type="password"
                value={form.password}
                placeholder={config ? st.fields.passwordKeepPlaceholder : ""}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </label>
            <label className={styles.fieldCheckbox}>
              <input
                type="checkbox"
                checked={form.verify_ssl}
                onChange={(e) => setForm({ ...form, verify_ssl: e.target.checked })}
              />
              <span>{st.fields.verifySsl}</span>
            </label>
          </div>

          {formError && <p className={styles.formError}>{formError}</p>}

          <div className={styles.formActions}>
            <button type="button" className={styles.saveButton} onClick={handleSave} disabled={saving}>
              {saving ? t.common.loading : st.save}
            </button>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={handleTest}
              disabled={testing || !form.host}
            >
              {testing ? t.common.loading : st.testConnection}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
