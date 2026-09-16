"use client";

import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
  createPamRule,
  deletePamRule,
  fetchAdGroups,
  fetchAssets,
  fetchPamRules,
  fetchPamTags,
  fetchPamUsers,
  fetchServerGroups,
  fetchVaultCredentials,
  updatePamRule,
  type AdGroup,
  type Asset,
  type CurrentUser,
  type PamAccessRule,
  type PamTag,
  type ServerGroup,
  type VaultCredential,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentsList.module.css";
import { ConfirmModal } from "./ConfirmModal";
import editModalStyles from "./EditRuleModal.module.css";
import { ToastStack, useToasts } from "./Toast";

// Faz 54 — "Geçerlilik Tarihi" sütununa kalan zamanı ekler. Süresiz
// kurallar için (`valid_until === null`) hiç çağrılmaz. Faz 58 — export
// edildi, `MyAccessPanel.tsx` da AYNI hesaplamayı reuse ediyor.
export function daysRemainingLabel(validUntil: string, formatDays: (n: number) => string, expiredLabel: string): string {
  const diffMs = new Date(validUntil).getTime() - Date.now();
  if (diffMs <= 0) return expiredLabel;
  const days = Math.ceil(diffMs / (24 * 60 * 60 * 1000));
  return formatDays(days);
}

// Faz 55 — cihaz hedefi artık üç kademeli: tek cihaz/etiket/cihaz
// grubu, TAM OLARAK biri dolu (bkz. backend'in `pam_access_rules_
// device_target_xor` CHECK constraint'i).
function deviceTargetLabel(rule: PamAccessRule): string {
  if (rule.tag_id) return `🏷️ ${rule.tag_name}`;
  if (rule.server_group_id) return `🗂️ ${rule.server_group_name}`;
  return rule.asset_hostname || rule.asset_ip_address || "—";
}

export function PamRulesPanel() {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const [rules, setRules] = useState<PamAccessRule[] | null>(null);
  const [users, setUsers] = useState<CurrentUser[]>([]);
  const [adGroups, setAdGroups] = useState<AdGroup[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [credentials, setCredentials] = useState<VaultCredential[]>([]);
  const [tags, setTags] = useState<PamTag[]>([]);
  const [serverGroups, setServerGroups] = useState<ServerGroup[]>([]);
  const [error, setError] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [targetType, setTargetType] = useState<"local" | "ad_group">("local");
  const [userId, setUserId] = useState("");
  const [adGroupId, setAdGroupId] = useState("");
  // Faz 55 — cihaz hedefi artık tek bir asset SEÇİMİ değil, üç
  // olasılıktan biri: tek cihaz / etiket / cihaz grubu.
  const [deviceTargetType, setDeviceTargetType] = useState<"asset" | "tag" | "server_group">("asset");
  const [assetId, setAssetId] = useState("");
  const [tagId, setTagId] = useState("");
  const [serverGroupId, setServerGroupId] = useState("");
  const [credentialId, setCredentialId] = useState("");
  const [allowRdp, setAllowRdp] = useState(false);
  const [allowSsh, setAllowSsh] = useState(true);
  const [allowWeb, setAllowWeb] = useState(false);
  const [maxDuration, setMaxDuration] = useState(60);
  const [validUntil, setValidUntil] = useState("");
  const [saving, setSaving] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<PamAccessRule | null>(null);
  const [editingRule, setEditingRule] = useState<PamAccessRule | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const { toasts, push, dismiss } = useToasts();

  // Faz 54 — arama barı (kullanıcı/AD grubu/cihaz/kasa hesabı adında).
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  async function load() {
    if (!token) return;
    try {
      const [rulesData, usersData, adGroupsData, assetsData, credentialsData, tagsData, serverGroupsData] = await Promise.all([
        fetchPamRules(token, { search: search || undefined }),
        fetchPamUsers(token),
        fetchAdGroups(token),
        fetchAssets(),
        fetchVaultCredentials(token),
        fetchPamTags(token),
        fetchServerGroups(token),
      ]);
      setRules(rulesData);
      setUsers(usersData);
      setAdGroups(adGroupsData);
      setAssets(assetsData);
      setCredentials(credentialsData);
      setTags(tagsData);
      setServerGroups(serverGroupsData);
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
  }, [token, search]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSaving(true);
    try {
      await createPamRule(token, {
        ...(targetType === "local" ? { user_id: userId } : { ad_group_id: adGroupId }),
        ...(deviceTargetType === "asset"
          ? { asset_id: assetId }
          : deviceTargetType === "tag"
            ? { tag_id: tagId }
            : { server_group_id: serverGroupId }),
        credential_id: credentialId,
        allow_rdp: allowRdp,
        allow_ssh: allowSsh,
        allow_web: allowWeb,
        max_session_duration_mins: maxDuration,
        valid_until: validUntil ? new Date(validUntil).toISOString() : null,
      });
      setShowForm(false);
      setValidUntil("");
      setUserId("");
      setAdGroupId("");
      setAssetId("");
      setTagId("");
      setServerGroupId("");
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : p.createRuleError);
    } finally {
      setSaving(false);
    }
  }

  async function handleConfirmDelete() {
    if (!token || !pendingDelete) return;
    try {
      await deletePamRule(token, pendingDelete.id);
      setPendingDelete(null);
      await load();
    } catch {
      setPendingDelete(null);
    }
  }

  async function handleToggleActive(rule: PamAccessRule) {
    if (!token) return;
    setTogglingId(rule.id);
    try {
      await updatePamRule(token, rule.id, { is_active: !rule.is_active });
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : p.saveRuleError);
    } finally {
      setTogglingId(null);
    }
  }

  const activeCredentialOptions = useMemo(() => credentials, [credentials]);

  return (
    <section className={styles.card}>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>{p.rulesTitle}</h2>
          <p className={styles.subtitle}>{p.rulesSubtitle}</p>
        </div>
        <button type="button" className={styles.toolbarButton} onClick={() => setShowForm((v) => !v)}>
          {p.newRule}
        </button>
      </div>

      <div className={styles.filterBar}>
        <input
          type="text"
          className={styles.searchInput}
          placeholder={p.rulesSearchPlaceholder}
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
      </div>

      {showForm && (
        <form onSubmit={handleCreate} style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
          <label className={styles.status}>
            {p.targetType}
            <br />
            <select
              className={styles.searchInput}
              value={targetType}
              onChange={(e) => setTargetType(e.target.value as "local" | "ad_group")}
            >
              <option value="local">{p.targetTypeLocal}</option>
              <option value="ad_group">{p.targetTypeAdGroup}</option>
            </select>
          </label>
          {targetType === "local" ? (
            <label className={styles.status}>
              {p.columnUser}
              <br />
              <select className={styles.searchInput} value={userId} onChange={(e) => setUserId(e.target.value)} required>
                <option value="" disabled>
                  —
                </option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.username} ({u.role})
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <label className={styles.status}>
              {p.columnAdGroup}
              <br />
              <select
                className={styles.searchInput}
                value={adGroupId}
                onChange={(e) => setAdGroupId(e.target.value)}
                required
              >
                <option value="" disabled>
                  —
                </option>
                {adGroups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
              {adGroups.length === 0 && <span className={styles.status}>{p.noAdGroups}</span>}
            </label>
          )}
          <label className={styles.status}>
            {p.deviceTargetType}
            <br />
            <select
              className={styles.searchInput}
              value={deviceTargetType}
              onChange={(e) => setDeviceTargetType(e.target.value as "asset" | "tag" | "server_group")}
            >
              <option value="asset">{p.deviceTargetAsset}</option>
              <option value="tag">{p.deviceTargetTag}</option>
              <option value="server_group">{p.deviceTargetGroup}</option>
            </select>
          </label>
          {deviceTargetType === "asset" && (
            <label className={styles.status}>
              {p.columnAsset}
              <br />
              <select className={styles.searchInput} value={assetId} onChange={(e) => setAssetId(e.target.value)} required>
                <option value="" disabled>
                  —
                </option>
                {assets.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.hostname || a.ip_address}
                  </option>
                ))}
              </select>
            </label>
          )}
          {deviceTargetType === "tag" && (
            <label className={styles.status}>
              {p.columnTag}
              <br />
              <select className={styles.searchInput} value={tagId} onChange={(e) => setTagId(e.target.value)} required>
                <option value="" disabled>
                  —
                </option>
                {tags.map((tg) => (
                  <option key={tg.id} value={tg.id}>
                    {tg.name}
                  </option>
                ))}
              </select>
              {tags.length === 0 && <span className={styles.status}>{p.noTags}</span>}
            </label>
          )}
          {deviceTargetType === "server_group" && (
            <label className={styles.status}>
              {p.columnServerGroup}
              <br />
              <select
                className={styles.searchInput}
                value={serverGroupId}
                onChange={(e) => setServerGroupId(e.target.value)}
                required
              >
                <option value="" disabled>
                  —
                </option>
                {serverGroups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
              {serverGroups.length === 0 && <span className={styles.status}>{p.noServerGroups}</span>}
            </label>
          )}
          <label className={styles.status}>
            {p.columnCredential}
            <br />
            <select
              className={styles.searchInput}
              value={credentialId}
              onChange={(e) => setCredentialId(e.target.value)}
              required
            >
              <option value="" disabled>
                —
              </option>
              {activeCredentialOptions.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.checkboxRow}>
            <input type="checkbox" checked={allowSsh} onChange={(e) => setAllowSsh(e.target.checked)} />
            {p.columnSsh}
          </label>
          <label className={styles.checkboxRow}>
            <input type="checkbox" checked={allowRdp} onChange={(e) => setAllowRdp(e.target.checked)} />
            {p.columnRdp}
          </label>
          <label className={styles.checkboxRow}>
            <input type="checkbox" checked={allowWeb} onChange={(e) => setAllowWeb(e.target.checked)} />
            {p.columnWeb}
          </label>
          <label className={styles.status}>
            {p.columnMaxDuration}
            <br />
            <input
              type="number"
              min={1}
              className={styles.searchInput}
              value={maxDuration}
              onChange={(e) => setMaxDuration(Number(e.target.value))}
              required
            />
          </label>
          <label className={styles.status}>
            {p.columnValidUntil}
            <br />
            <input
              type="datetime-local"
              className={styles.searchInput}
              value={validUntil}
              onChange={(e) => setValidUntil(e.target.value)}
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
      {!error && rules === null && <p className={styles.status}>{t.common.loading}</p>}
      {!error && rules !== null && rules.length === 0 && <p className={styles.status}>{t.common.noDataAvailable}</p>}

      {!error && rules !== null && rules.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{p.columnUser}</th>
                <th>{p.columnAsset}</th>
                <th>{p.columnCredential}</th>
                <th>{p.columnSsh}</th>
                <th>{p.columnRdp}</th>
                <th>{p.columnWeb}</th>
                <th>{p.columnMaxDuration}</th>
                <th>{p.columnValidUntil}</th>
                <th>{p.columnActions}</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.id} className={rule.is_active ? undefined : styles.ruleInactiveRow}>
                  <td>{rule.username ?? `${p.columnAdGroup}: ${rule.ad_group_name}`}</td>
                  <td>{deviceTargetLabel(rule)}</td>
                  <td>{rule.credential_name}</td>
                  <td>
                    <span className={`${styles.badge} ${rule.allow_ssh ? styles.badgeGreen : styles.badgeRed}`}>
                      {rule.allow_ssh ? "✅" : "❌"} SSH
                    </span>
                  </td>
                  <td>
                    <span className={`${styles.badge} ${rule.allow_rdp ? styles.badgeGreen : styles.badgeRed}`}>
                      {rule.allow_rdp ? "✅" : "❌"} RDP
                    </span>
                  </td>
                  <td>
                    <span className={`${styles.badge} ${rule.allow_web ? styles.badgeGreen : styles.badgeRed}`}>
                      {rule.allow_web ? "✅" : "❌"} Web
                    </span>
                  </td>
                  <td>{rule.max_session_duration_mins}</td>
                  <td>
                    {rule.valid_until ? (
                      <>
                        {new Date(rule.valid_until).toLocaleDateString()}{" "}
                        <span className={styles.status}>
                          ({daysRemainingLabel(rule.valid_until, p.daysRemaining, p.expired)})
                        </span>
                      </>
                    ) : (
                      p.unlimited
                    )}
                  </td>
                  <td className={styles.actionsCell}>
                    <label className={styles.toggleSwitch} title={rule.is_active ? p.active : p.inactive}>
                      <input
                        type="checkbox"
                        checked={rule.is_active}
                        disabled={togglingId === rule.id}
                        onChange={() => handleToggleActive(rule)}
                      />
                      <span className={styles.toggleTrack} />
                    </label>
                    <button type="button" className={styles.actionButton} onClick={() => setEditingRule(rule)}>
                      {p.editRule}
                    </button>
                    <button
                      type="button"
                      className={`${styles.actionButton} ${styles.actionButtonDanger}`}
                      onClick={() => setPendingDelete(rule)}
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
          message={p.confirmDeleteRule}
          confirmLabel={p.delete}
          cancelLabel={p.cancel}
          onConfirm={handleConfirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}

      {editingRule && (
        <EditRuleModal
          rule={editingRule}
          credentials={activeCredentialOptions}
          onClose={() => setEditingRule(null)}
          onSaved={() => {
            setEditingRule(null);
            load();
          }}
        />
      )}
    </section>
  );
}

// Faz 54 — "Kuralı Düzenle" modalı. Hedef (kullanıcı/AD grubu) ve cihaz
// backend'in `PamAccessRuleUpdateRequest`'inde zaten DEĞİŞTİRİLEMEZ
// (yalnızca kasa hesabı/izinler/süre/geçerlilik/aktiflik) — bu yüzden
// bu modal SADECE o alanları düzenler, ayrı bir "hedefi taşı" akışı
// KASITLI olarak yok.
function EditRuleModal({
  rule,
  credentials,
  onClose,
  onSaved,
}: {
  rule: PamAccessRule;
  credentials: VaultCredential[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const [credentialId, setCredentialId] = useState(rule.credential_id);
  const [allowSsh, setAllowSsh] = useState(rule.allow_ssh);
  const [allowRdp, setAllowRdp] = useState(rule.allow_rdp);
  const [allowWeb, setAllowWeb] = useState(rule.allow_web);
  const [maxDuration, setMaxDuration] = useState(rule.max_session_duration_mins);
  const [validUntil, setValidUntil] = useState(
    rule.valid_until ? new Date(rule.valid_until).toISOString().slice(0, 16) : "",
  );
  const [saving, setSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSaving(true);
    setErrorMessage(null);
    try {
      await updatePamRule(token, rule.id, {
        credential_id: credentialId,
        allow_ssh: allowSsh,
        allow_rdp: allowRdp,
        allow_web: allowWeb,
        max_session_duration_mins: maxDuration,
        valid_until: validUntil ? new Date(validUntil).toISOString() : null,
      });
      onSaved();
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : p.saveRuleError);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={editModalStyles.overlay} role="presentation" onClick={onClose}>
      <form
        onSubmit={handleSubmit}
        role="dialog"
        aria-modal="true"
        className={editModalStyles.dialog}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className={editModalStyles.title}>{p.editRuleTitle}</h3>
        <p className={editModalStyles.subtitle}>
          {rule.username ?? `${p.columnAdGroup}: ${rule.ad_group_name}`} → {deviceTargetLabel(rule)}
        </p>

        {errorMessage && (
          <p className={styles.error} role="alert">
            {errorMessage}
          </p>
        )}

        <label className={styles.status}>
          {p.columnCredential}
          <br />
          <select
            className={styles.searchInput}
            value={credentialId}
            onChange={(e) => setCredentialId(e.target.value)}
            required
          >
            {credentials.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.checkboxRow}>
          <input type="checkbox" checked={allowSsh} onChange={(e) => setAllowSsh(e.target.checked)} />
          {p.columnSsh}
        </label>
        <label className={styles.checkboxRow}>
          <input type="checkbox" checked={allowRdp} onChange={(e) => setAllowRdp(e.target.checked)} />
          {p.columnRdp}
        </label>
        <label className={styles.checkboxRow}>
          <input type="checkbox" checked={allowWeb} onChange={(e) => setAllowWeb(e.target.checked)} />
          {p.columnWeb}
        </label>
        <label className={styles.status}>
          {p.columnMaxDuration}
          <br />
          <input
            type="number"
            min={1}
            className={styles.searchInput}
            value={maxDuration}
            onChange={(e) => setMaxDuration(Number(e.target.value))}
            required
          />
        </label>
        <label className={styles.status}>
          {p.columnValidUntil}
          <br />
          <input
            type="datetime-local"
            className={styles.searchInput}
            value={validUntil}
            onChange={(e) => setValidUntil(e.target.value)}
          />
        </label>

        <div className={editModalStyles.actions}>
          <button type="button" className={styles.actionButton} onClick={onClose}>
            {p.cancel}
          </button>
          <button type="submit" className={styles.toolbarButton} disabled={saving}>
            {p.save}
          </button>
        </div>
      </form>
    </div>
  );
}
