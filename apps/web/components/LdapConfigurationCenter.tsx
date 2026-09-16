"use client";

import { useEffect, useState } from "react";

import { fetchLdapConfig, syncLdapDirectory, testLdapConnection, updateLdapConfig, type LdapConfig, type LdapConfigRequest, type LdapSyncResult } from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { ToastStack, useToasts } from "./Toast";
import styles from "./LdapConfigurationCenter.module.css";

type FetchStatus = "loading" | "done" | "error";

type FormState = {
  host: string;
  port: string;
  use_ssl: boolean;
  domain_fqdn: string;
  base_dn: string;
  bind_dn: string;
  bind_password: string;
};

const EMPTY_FORM: FormState = {
  host: "",
  port: "389",
  use_ssl: false,
  domain_fqdn: "",
  base_dn: "",
  bind_dn: "",
  bind_password: "",
};

function configToForm(config: LdapConfig): FormState {
  return {
    host: config.host,
    port: String(config.port),
    use_ssl: config.use_ssl,
    domain_fqdn: config.domain_fqdn,
    base_dn: config.base_dn,
    bind_dn: config.bind_dn,
    // Bind parolası HİÇBİR ZAMAN düz metin olarak backend'den dönmez
    // (bkz. LdapConfigResponse.bind_password_masked) — boş bırakılır,
    // kullanıcı yalnızca DEĞİŞTİRMEK istediğinde doldurur.
    bind_password: "",
  };
}

function formToPayload(form: FormState): LdapConfigRequest {
  return {
    host: form.host.trim(),
    port: Number(form.port),
    use_ssl: form.use_ssl,
    domain_fqdn: form.domain_fqdn.trim(),
    base_dn: form.base_dn.trim(),
    bind_dn: form.bind_dn.trim(),
    // Boş string DEĞİL `null` gönderilmeli — backend `bind_password:
    // str | None`'da boş string'i (Pydantic `min_length=1`) GEÇERSİZ
    // sayar, yalnızca `null`/alan hiç gönderilmemesi "değiştirme"
    // anlamına gelir (bkz. app/routes/ldap_settings.py::
    // _resolve_bind_password).
    bind_password: form.bind_password || null,
  };
}

export function LdapConfigurationCenter() {
  const { token } = useAuth();
  const { t } = useLocale();
  const lt = t.settings.ldapConfig;

  const [config, setConfig] = useState<LdapConfig | null>(null);
  const [status, setStatus] = useState<FetchStatus>("loading");
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [lastSyncResult, setLastSyncResult] = useState<LdapSyncResult | null>(null);
  const { toasts, push: pushToast, dismiss: dismissToast } = useToasts();

  function load() {
    if (!token) return;
    fetchLdapConfig(token)
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
      const saved = await updateLdapConfig(token, formToPayload(form));
      setConfig(saved);
      setForm(configToForm(saved));
      pushToast("success", lt.save);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : lt.saveError);
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    if (!token) return;
    setTesting(true);
    try {
      const result = await testLdapConnection(token, formToPayload(form));
      pushToast(result.success ? "success" : "error", `${result.success ? lt.testSuccess : lt.testError}: ${result.message}`);
    } catch (err) {
      pushToast("error", err instanceof Error ? err.message : lt.testError);
    } finally {
      setTesting(false);
    }
  }

  async function handleSync() {
    if (!token) return;
    setSyncing(true);
    try {
      const result = await syncLdapDirectory(token);
      setLastSyncResult(result);
      pushToast("success", lt.syncResult(result.groups_synced, result.users_synced, result.memberships_synced));
      load();
    } catch (err) {
      pushToast("error", err instanceof Error ? err.message : lt.syncError);
    } finally {
      setSyncing(false);
    }
  }

  return (
    <section className={styles.card}>
      <ToastStack toasts={toasts} onDismiss={dismissToast} />
      <div className={styles.header}>
        <h3 className={styles.sectionTitle}>{lt.sectionTitle}</h3>
        <p className={styles.description}>{lt.description}</p>
      </div>

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {status === "error" && <p className={styles.status}>{lt.loadError}</p>}

      {status === "done" && (
        <>
          {config === null && <p className={styles.noData}>{lt.notConfigured}</p>}

          {config !== null && (
            <div className={styles.syncSummary}>
              <span className={styles.statusCell}>
                <span
                  className={`${styles.dot} ${
                    config.last_sync_status === "success"
                      ? styles.dotReady
                      : config.last_sync_status === "error"
                        ? styles.dotDown
                        : styles.dotMuted
                  }`}
                />
                {lt.lastSync}:{" "}
                {config.last_sync_at
                  ? new Date(config.last_sync_at).toLocaleString()
                  : lt.lastSyncNever}
                {config.last_sync_status === "success" && ` — ${lt.lastSyncStatusSuccess}`}
                {config.last_sync_status === "error" && ` — ${lt.lastSyncStatusError}`}
              </span>
              {config.last_sync_status === "error" && config.last_sync_error && (
                <span className={styles.formError}>{config.last_sync_error}</span>
              )}
              {lastSyncResult && (
                <span>
                  {lt.syncResult(
                    lastSyncResult.groups_synced,
                    lastSyncResult.users_synced,
                    lastSyncResult.memberships_synced,
                  )}
                </span>
              )}
            </div>
          )}

          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span>{lt.fields.host}</span>
              <input
                type="text"
                value={form.host}
                placeholder={lt.fields.hostPlaceholder}
                onChange={(e) => setForm({ ...form, host: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span>{lt.fields.port}</span>
              <input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} />
            </label>
            <label className={styles.fieldCheckbox}>
              <input
                type="checkbox"
                checked={form.use_ssl}
                onChange={(e) => setForm({ ...form, use_ssl: e.target.checked })}
              />
              <span>{lt.fields.useSsl}</span>
            </label>
            <label className={styles.field}>
              <span>{lt.fields.domainFqdn}</span>
              <input
                type="text"
                value={form.domain_fqdn}
                placeholder={lt.fields.domainFqdnPlaceholder}
                onChange={(e) => setForm({ ...form, domain_fqdn: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span>{lt.fields.baseDn}</span>
              <input
                type="text"
                value={form.base_dn}
                placeholder={lt.fields.baseDnPlaceholder}
                onChange={(e) => setForm({ ...form, base_dn: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span>{lt.fields.bindDn}</span>
              <input
                type="text"
                value={form.bind_dn}
                placeholder={lt.fields.bindDnPlaceholder}
                onChange={(e) => setForm({ ...form, bind_dn: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span>{lt.fields.bindPassword}</span>
              <input
                type="password"
                value={form.bind_password}
                placeholder={lt.fields.bindPasswordPlaceholder}
                onChange={(e) => setForm({ ...form, bind_password: e.target.value })}
              />
            </label>
          </div>

          {formError && <p className={styles.formError}>{formError}</p>}

          <div className={styles.formActions}>
            <button type="button" className={styles.saveButton} onClick={handleSave} disabled={saving}>
              {saving ? lt.saving : lt.save}
            </button>
            <button type="button" className={styles.secondaryButton} onClick={handleTest} disabled={testing}>
              {testing ? lt.testing : lt.testConnection}
            </button>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={handleSync}
              disabled={syncing || config === null}
            >
              {syncing ? lt.syncing : lt.syncNow}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
