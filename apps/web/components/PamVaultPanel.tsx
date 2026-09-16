"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  createVaultCredential,
  deleteVaultCredential,
  fetchVaultCredentials,
  revealVaultCredential,
  type VaultCredential,
  type VaultCredentialType,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentsList.module.css";
import { ConfirmModal } from "./ConfirmModal";
import { ToastStack, useToasts } from "./Toast";

export function PamVaultPanel() {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const [credentials, setCredentials] = useState<VaultCredential[] | null>(null);
  const [error, setError] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [credentialType, setCredentialType] = useState<VaultCredentialType>("password");
  const [username, setUsername] = useState("");
  const [domain, setDomain] = useState("");
  const [secret, setSecret] = useState("");
  const [saving, setSaving] = useState(false);
  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const [pendingDelete, setPendingDelete] = useState<VaultCredential | null>(null);
  const { toasts, push, dismiss } = useToasts();

  async function load() {
    if (!token) return;
    try {
      setCredentials(await fetchVaultCredentials(token));
      setError(false);
    } catch {
      setError(true);
    }
  }

  useEffect(() => {
    // setState çağrıları bir microtask'a ertelendi — bkz. `lib/i18n/
    // LocaleProvider.tsx`'teki aynı desen (react-hooks/set-state-in-effect).
    Promise.resolve().then(() => {
      load();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSaving(true);
    try {
      await createVaultCredential(token, {
        name,
        credential_type: credentialType,
        username,
        domain: domain || null,
        password: credentialType === "password" ? secret : null,
        private_key: credentialType === "ssh_key" ? secret : null,
      });
      setName("");
      setUsername("");
      setDomain("");
      setSecret("");
      setShowForm(false);
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : p.createCredentialError);
    } finally {
      setSaving(false);
    }
  }

  async function handleToggleReveal(credential: VaultCredential) {
    if (!token) return;
    if (revealed[credential.id] !== undefined) {
      setRevealed((prev) => {
        const next = { ...prev };
        delete next[credential.id];
        return next;
      });
      return;
    }
    try {
      const result = await revealVaultCredential(token, credential.id);
      setRevealed((prev) => ({ ...prev, [credential.id]: result.password || result.private_key || "" }));
    } catch {
      push("error", p.revealError);
    }
  }

  async function handleConfirmDelete() {
    if (!token || !pendingDelete) return;
    try {
      await deleteVaultCredential(token, pendingDelete.id);
      setPendingDelete(null);
      await load();
    } catch (err) {
      push("error", err instanceof ApiError && err.status === 409 ? p.deleteCredentialInUse : (err as Error).message);
      setPendingDelete(null);
    }
  }

  return (
    <section className={styles.card}>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>{p.vaultTitle}</h2>
          <p className={styles.subtitle}>{p.vaultSubtitle}</p>
        </div>
        <button type="button" className={styles.toolbarButton} onClick={() => setShowForm((v) => !v)}>
          {p.newCredential}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
          <label className={styles.status}>
            {p.columnName}
            <br />
            <input className={styles.searchInput} value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label className={styles.status}>
            {p.columnType}
            <br />
            <select
              className={styles.searchInput}
              value={credentialType}
              onChange={(e) => setCredentialType(e.target.value as VaultCredentialType)}
            >
              <option value="password">{p.credentialTypePassword}</option>
              <option value="ssh_key">{p.credentialTypeSshKey}</option>
            </select>
          </label>
          <label className={styles.status}>
            {p.columnCredentialUsername}
            <br />
            <input
              className={styles.searchInput}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </label>
          <label className={styles.status}>
            Domain
            <br />
            <input className={styles.searchInput} value={domain} onChange={(e) => setDomain(e.target.value)} />
          </label>
          <label className={styles.status}>
            {credentialType === "password" ? t.auth.password : p.columnSecret}
            <br />
            <textarea
              className={styles.searchInput}
              style={{ minHeight: credentialType === "ssh_key" ? 80 : undefined, fontFamily: credentialType === "ssh_key" ? "monospace" : undefined }}
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              required
            />
          </label>
          <button type="submit" className={styles.toolbarButton} disabled={saving}>
            {p.create}
          </button>
        </form>
      )}

      {error && (
        <p className={styles.error} role="alert">
          {t.common.unableToLoad}
        </p>
      )}
      {!error && credentials === null && <p className={styles.status}>{t.common.loading}</p>}
      {!error && credentials !== null && credentials.length === 0 && (
        <p className={styles.status}>{t.common.noDataAvailable}</p>
      )}

      {!error && credentials !== null && credentials.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{p.columnName}</th>
                <th>{p.columnType}</th>
                <th>{p.columnCredentialUsername}</th>
                <th>{p.columnSecret}</th>
                <th>{p.columnActions}</th>
              </tr>
            </thead>
            <tbody>
              {credentials.map((credential) => (
                <tr key={credential.id}>
                  <td>{credential.name}</td>
                  <td>
                    {credential.credential_type === "password" ? p.credentialTypePassword : p.credentialTypeSshKey}
                  </td>
                  <td>{credential.username}</td>
                  <td className={styles.mono}>{revealed[credential.id] ?? credential.secret_masked}</td>
                  <td className={styles.actionsCell}>
                    <button type="button" className={styles.actionButton} onClick={() => handleToggleReveal(credential)}>
                      {revealed[credential.id] !== undefined ? p.hide : p.show}
                    </button>
                    <button
                      type="button"
                      className={`${styles.actionButton} ${styles.actionButtonDanger}`}
                      onClick={() => setPendingDelete(credential)}
                    >
                      {p.delete}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pendingDelete && (
        <ConfirmModal
          title={p.delete}
          message={p.confirmDeleteCredential}
          confirmLabel={p.delete}
          cancelLabel={p.cancel}
          onConfirm={handleConfirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </section>
  );
}
