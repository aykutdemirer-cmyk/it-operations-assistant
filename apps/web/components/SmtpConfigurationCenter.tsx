"use client";

import { useEffect, useState } from "react";

import {
  fetchSmtpConfig,
  testSmtpConnection,
  updateSmtpConfig,
  type SmtpConfig,
  type SmtpConfigRequest,
  type SmtpEncryption,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { ToastStack, useToasts } from "./Toast";
// LDAP yapılandırma merkeziyle AYNI görsel dil — stiller yeniden kullanılıyor.
import styles from "./LdapConfigurationCenter.module.css";

type FetchStatus = "loading" | "done" | "error";

type FormState = {
  enabled: boolean;
  server: string;
  port: string;
  encryption: SmtpEncryption;
  username: string;
  password: string;
  from_email: string;
  from_name: string;
  it_group_email: string;
  base_url: string;
};

const EMPTY_FORM: FormState = {
  enabled: true,
  server: "",
  port: "587",
  encryption: "tls",
  username: "",
  password: "",
  from_email: "",
  from_name: "IT Operations Helpdesk",
  it_group_email: "",
  base_url: "",
};

function configToForm(config: SmtpConfig): FormState {
  return {
    enabled: config.enabled,
    server: config.server,
    port: String(config.port),
    encryption: config.encryption,
    username: config.username,
    // Parola HİÇBİR ZAMAN düz metin dönmez — boş bırakılır.
    password: "",
    from_email: config.from_email,
    from_name: config.from_name,
    it_group_email: config.it_group_email,
    base_url: config.base_url,
  };
}

function formToPayload(form: FormState): SmtpConfigRequest {
  return {
    enabled: form.enabled,
    server: form.server.trim(),
    port: Number(form.port),
    encryption: form.encryption,
    username: form.username.trim(),
    // Boş → null ("mevcut parolayı koru").
    password: form.password || null,
    from_email: form.from_email.trim(),
    from_name: form.from_name.trim(),
    it_group_email: form.it_group_email.trim(),
    base_url: form.base_url.trim(),
  };
}

// Port alanı — şifreleme türü değişince kullanıcı için tipik portu
// öneri olarak doldurur (yalnızca alan hâlâ bir önceki türün varsayılanı
// İSE — elle girilmiş bir port asla ÜZERİNE YAZILMAZ).
const TYPICAL_PORT: Record<SmtpEncryption, string> = { tls: "587", ssl: "465", none: "25" };

export function SmtpConfigurationCenter() {
  const { token } = useAuth();
  const { t } = useLocale();
  const st = t.settings.smtpConfig;

  const [config, setConfig] = useState<SmtpConfig | null>(null);
  const [status, setStatus] = useState<FetchStatus>("loading");
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [testTo, setTestTo] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const { toasts, push: pushToast, dismiss: dismissToast } = useToasts();

  function load() {
    if (!token) return;
    fetchSmtpConfig(token)
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
      const saved = await updateSmtpConfig(token, formToPayload(form));
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
      const result = await testSmtpConnection(token, testTo.trim());
      pushToast(
        result.success ? "success" : "error",
        `${result.success ? st.testSuccess : st.testError}: ${result.message}`,
      );
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
                {st.lastTest}:{" "}
                {config.last_test_at ? new Date(config.last_test_at).toLocaleString() : st.lastTestNever}
                {config.last_test_status === "success" && ` — ${st.lastTestStatusSuccess}`}
                {config.last_test_status === "error" && ` — ${st.lastTestStatusError}`}
              </span>
              {config.last_test_status === "error" && config.last_test_error && (
                <span className={styles.formError}>{config.last_test_error}</span>
              )}
            </div>
          )}

          <div className={styles.formGrid}>
            <label className={styles.fieldCheckbox}>
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
              />
              <span>{st.enabled}</span>
            </label>
            <label className={styles.field}>
              <span>{st.fields.server}</span>
              <input
                type="text"
                value={form.server}
                placeholder={st.fields.serverPlaceholder}
                onChange={(e) => setForm({ ...form, server: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span>{st.fields.port}</span>
              <input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} />
            </label>
            <label className={styles.field}>
              <span>{st.fields.encryption}</span>
              <select
                value={form.encryption}
                onChange={(e) => {
                  const encryption = e.target.value as SmtpEncryption;
                  setForm((f) => ({
                    ...f,
                    encryption,
                    // Port hâlâ ÖNCEKİ türün tipik değeriyse öner — elle
                    // girilmiş bir port asla üzerine yazılmaz.
                    port: f.port === TYPICAL_PORT[f.encryption] ? TYPICAL_PORT[encryption] : f.port,
                  }));
                }}
              >
                <option value="tls">{st.encryptionTls}</option>
                <option value="ssl">{st.encryptionSsl}</option>
                <option value="none">{st.encryptionNone}</option>
              </select>
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
                placeholder={st.fields.passwordPlaceholder}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span>{st.fields.fromEmail}</span>
              <input
                type="text"
                value={form.from_email}
                placeholder={st.fields.fromEmailPlaceholder}
                onChange={(e) => setForm({ ...form, from_email: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span>{st.fields.fromName}</span>
              <input
                type="text"
                value={form.from_name}
                placeholder={st.fields.fromNamePlaceholder}
                onChange={(e) => setForm({ ...form, from_name: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span>{st.fields.itGroupEmail}</span>
              <input
                type="text"
                value={form.it_group_email}
                placeholder={st.fields.itGroupEmailPlaceholder}
                onChange={(e) => setForm({ ...form, it_group_email: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span>{st.fields.baseUrl}</span>
              <input
                type="text"
                value={form.base_url}
                placeholder={st.fields.baseUrlPlaceholder}
                onChange={(e) => setForm({ ...form, base_url: e.target.value })}
              />
            </label>
          </div>

          {formError && <p className={styles.formError}>{formError}</p>}

          <div className={styles.formActions}>
            <button type="button" className={styles.saveButton} onClick={handleSave} disabled={saving}>
              {saving ? st.saving : st.save}
            </button>
          </div>

          <div className={styles.formGrid} style={{ marginTop: 12 }}>
            <label className={styles.field}>
              <span>{st.testTitle}</span>
              <input
                type="text"
                value={testTo}
                placeholder={st.testToPlaceholder}
                onChange={(e) => setTestTo(e.target.value)}
              />
            </label>
          </div>
          <div className={styles.formActions}>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={handleTest}
              disabled={testing || config === null}
            >
              {testing ? st.testing : st.testButton}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
