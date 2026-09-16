"use client";

import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
  createPamRule,
  deletePamRule,
  fetchAssets,
  fetchPamRules,
  fetchPamUser,
  fetchVaultCredentials,
  updatePamRule,
  type Asset,
  type CurrentUser,
  type PamAccessRule,
  type VaultCredential,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentsList.module.css";
import { ToastStack, useToasts } from "./Toast";

type RowState = {
  allowRdp: boolean;
  allowSsh: boolean;
  credentialId: string;
  validUntil: string;
};

function ruleToRowState(rule: PamAccessRule | undefined): RowState {
  return {
    allowRdp: rule?.allow_rdp ?? false,
    allowSsh: rule?.allow_ssh ?? false,
    credentialId: rule?.credential_id ?? "",
    validUntil: rule?.valid_until ? rule.valid_until.slice(0, 16) : "",
  };
}

function rowStateEquals(a: RowState, b: RowState): boolean {
  return a.allowRdp === b.allowRdp && a.allowSsh === b.allowSsh && a.credentialId === b.credentialId && a.validUntil === b.validUntil;
}

/** Faz 47 — `/pam/users/{userId}` Cihaz Erişim Matrisi. Kullanıcının
 * açık isteğindeki mockup'ın karşılığı: her cihaz için ayrı RDP/SSH
 * checkbox'ları + (yalnızca işaretliyken görünen) kasa hesabı seçimi +
 * opsiyonel süre. Mevcut `pam_access_rules` CRUD API'sini (Faz 46)
 * KULLANIR — yeni bir "batch" endpoint EKLENMEDİ, her satır kendi
 * create/update/delete çağrısını yapar. */
export function UserDeviceAccessPanel({ userId }: { userId: string }) {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const [user, setUser] = useState<CurrentUser | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [credentials, setCredentials] = useState<VaultCredential[]>([]);
  const [rules, setRules] = useState<PamAccessRule[]>([]);
  const [edits, setEdits] = useState<Record<string, RowState>>({});
  const [savingAssetId, setSavingAssetId] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const { toasts, push, dismiss } = useToasts();

  async function load() {
    if (!token) return;
    try {
      const [userData, assetsData, credentialsData, rulesData] = await Promise.all([
        fetchPamUser(token, userId),
        fetchAssets(),
        fetchVaultCredentials(token),
        fetchPamRules(token),
      ]);
      setUser(userData);
      setAssets(assetsData);
      setCredentials(credentialsData);
      const userRules = rulesData.filter((rule) => rule.user_id === userId);
      setRules(userRules);
      setEdits(
        Object.fromEntries(assetsData.map((asset) => [asset.id, ruleToRowState(userRules.find((r) => r.asset_id === asset.id))])),
      );
      setError(false);
    } catch {
      setError(true);
    }
  }

  useEffect(() => {
    Promise.resolve().then(() => {
      load();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, userId]);

  const rulesByAsset = useMemo(() => new Map(rules.map((r) => [r.asset_id, r])), [rules]);

  function updateRow(assetId: string, patch: Partial<RowState>) {
    setEdits((prev) => ({ ...prev, [assetId]: { ...prev[assetId], ...patch } }));
  }

  async function saveRow(asset: Asset) {
    if (!token) return;
    const row = edits[asset.id];
    const existingRule = rulesByAsset.get(asset.id);
    setSavingAssetId(asset.id);
    try {
      if (!row.allowRdp && !row.allowSsh) {
        if (existingRule) await deletePamRule(token, existingRule.id);
      } else {
        if (!row.credentialId) {
          push("error", p.deviceAccessNoCredential);
          return;
        }
        const validUntilIso = row.validUntil ? new Date(row.validUntil).toISOString() : null;
        if (existingRule) {
          await updatePamRule(token, existingRule.id, {
            credential_id: row.credentialId,
            allow_rdp: row.allowRdp,
            allow_ssh: row.allowSsh,
            valid_until: validUntilIso,
          });
        } else {
          await createPamRule(token, {
            user_id: userId,
            asset_id: asset.id,
            credential_id: row.credentialId,
            allow_rdp: row.allowRdp,
            allow_ssh: row.allowSsh,
            valid_until: validUntilIso,
          });
        }
      }
      push("success", p.deviceAccessSaved);
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : p.deviceAccessSaveError);
    } finally {
      setSavingAssetId(null);
    }
  }

  if (error) {
    return (
      <p className={styles.error} role="alert">
        {t.common.unableToLoad}
      </p>
    );
  }

  if (!user) {
    return <p className={styles.status}>{t.common.loading}</p>;
  }

  return (
    <section className={styles.card}>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>
            {p.deviceAccessTitle} — {user.username}
          </h2>
          <p className={styles.subtitle}>{p.deviceAccessSubtitle}</p>
        </div>
      </div>

      {assets.length === 0 && <p className={styles.status}>{t.common.noDataAvailable}</p>}

      {assets.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{p.columnAsset}</th>
                <th>{p.columnSsh}</th>
                <th>{p.columnRdp}</th>
                <th>{p.columnCredential}</th>
                <th>{p.columnValidUntil}</th>
                <th>{p.columnActions}</th>
              </tr>
            </thead>
            <tbody>
              {assets.map((asset) => {
                const row = edits[asset.id] ?? ruleToRowState(undefined);
                const original = ruleToRowState(rulesByAsset.get(asset.id));
                const dirty = !rowStateEquals(row, original);
                return (
                  <tr key={asset.id}>
                    <td>{asset.hostname || asset.ip_address}</td>
                    <td>
                      <input
                        type="checkbox"
                        checked={row.allowSsh}
                        onChange={(e) => updateRow(asset.id, { allowSsh: e.target.checked })}
                      />
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={row.allowRdp}
                        onChange={(e) => updateRow(asset.id, { allowRdp: e.target.checked })}
                      />
                    </td>
                    <td>
                      <select
                        className={styles.searchInput}
                        value={row.credentialId}
                        onChange={(e) => updateRow(asset.id, { credentialId: e.target.value })}
                        disabled={!row.allowRdp && !row.allowSsh}
                      >
                        <option value="">—</option>
                        {credentials.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input
                        type="datetime-local"
                        className={styles.searchInput}
                        value={row.validUntil}
                        onChange={(e) => updateRow(asset.id, { validUntil: e.target.value })}
                        disabled={!row.allowRdp && !row.allowSsh}
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        className={styles.actionButton}
                        disabled={!dirty || savingAssetId === asset.id}
                        onClick={() => saveRow(asset)}
                      >
                        {p.save}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
