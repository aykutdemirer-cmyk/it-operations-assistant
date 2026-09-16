"use client";

import { useEffect, useState } from "react";

import {
  addServerGroupMember,
  ApiError,
  createServerGroup,
  deleteServerGroup,
  fetchAssets,
  fetchServerGroupAssets,
  fetchServerGroups,
  removeServerGroupMember,
  type Asset,
  type ServerGroup,
  type ServerGroupAsset,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentsList.module.css";
import { ConfirmModal } from "./ConfirmModal";
import modalStyles from "./EditRuleModal.module.css";
import { ToastStack, useToasts } from "./Toast";

/** Faz 55 — Statik Cihaz Grupları (Server Groups). Bir erişim kuralının
 * TEK bir cihaz YERİNE elle/statik bir gruba atanabilmesinin yönetim
 * ekranı — `PamRulesPanel.tsx`'in "Cihaz Hedefi Tipi" seçicisinde
 * kullanılır. Dinamik (kural-tabanlı, ör. "OS==Linux") gruplar KASITLI
 * olarak bu fazın kapsamı DIŞINDA (bkz. docs/roadmap.md Faz 55). */
export function PamServerGroupsPanel() {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const [groups, setGroups] = useState<ServerGroup[] | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [error, setError] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<ServerGroup | null>(null);
  const [managingGroup, setManagingGroup] = useState<ServerGroup | null>(null);
  const { toasts, push, dismiss } = useToasts();

  async function load() {
    if (!token) return;
    try {
      const [groupsData, assetsData] = await Promise.all([fetchServerGroups(token), fetchAssets()]);
      setGroups(groupsData);
      setAssets(assetsData);
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
  }, [token]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !newName.trim()) return;
    setSaving(true);
    try {
      await createServerGroup(token, newName.trim(), newDescription.trim() || null);
      setNewName("");
      setNewDescription("");
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : p.createGroupError);
    } finally {
      setSaving(false);
    }
  }

  async function handleConfirmDelete() {
    if (!token || !pendingDelete) return;
    try {
      await deleteServerGroup(token, pendingDelete.id);
      setPendingDelete(null);
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : p.deleteGroupError);
      setPendingDelete(null);
    }
  }

  return (
    <section className={styles.card}>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>{p.groupsTitle}</h2>
          <p className={styles.subtitle}>{p.groupsSubtitle}</p>
        </div>
      </div>

      <form onSubmit={handleCreate} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        <label className={styles.status}>
          {p.columnName}
          <br />
          <input
            type="text"
            className={styles.searchInput}
            placeholder={p.newGroupNamePlaceholder}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
        </label>
        <label className={styles.status}>
          {p.columnDescription}
          <br />
          <input
            type="text"
            className={styles.searchInput}
            placeholder={p.newGroupDescriptionPlaceholder}
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
          />
        </label>
        <button type="submit" className={styles.toolbarButton} disabled={saving || !newName.trim()}>
          {p.create}
        </button>
      </form>

      {error && (
        <p className={styles.error} role="alert">
          {t.common.unableToLoad}
        </p>
      )}
      {!error && groups === null && <p className={styles.status}>{t.common.loading}</p>}
      {!error && groups !== null && groups.length === 0 && <p className={styles.status}>{t.common.noDataAvailable}</p>}

      {!error && groups !== null && groups.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{p.columnName}</th>
                <th>{p.columnDescription}</th>
                <th>{p.columnActions}</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((group) => (
                <tr key={group.id}>
                  <td>
                    <span className={`${styles.badge} ${styles.badgeBlue}`}>🗂️ {group.name}</span>
                  </td>
                  <td>{group.description || "—"}</td>
                  <td className={styles.actionsCell}>
                    <button type="button" className={styles.actionButton} onClick={() => setManagingGroup(group)}>
                      {p.manageAssets}
                    </button>
                    <button
                      type="button"
                      className={`${styles.actionButton} ${styles.actionButtonDanger}`}
                      onClick={() => setPendingDelete(group)}
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
          message={p.confirmDeleteGroup}
          confirmLabel={p.delete}
          cancelLabel={p.cancel}
          onConfirm={handleConfirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}

      {managingGroup && (
        <ManageGroupAssetsModal group={managingGroup} allAssets={assets} onClose={() => setManagingGroup(null)} />
      )}
    </section>
  );
}

function ManageGroupAssetsModal({
  group,
  allAssets,
  onClose,
}: {
  group: ServerGroup;
  allAssets: Asset[];
  onClose: () => void;
}) {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const [memberIds, setMemberIds] = useState<Set<string> | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    fetchServerGroupAssets(token, group.id).then((rows: ServerGroupAsset[]) => setMemberIds(new Set(rows.map((r) => r.id))));
  }, [token, group.id]);

  async function toggle(assetId: string, isMember: boolean) {
    if (!token || !memberIds) return;
    setBusyId(assetId);
    try {
      if (isMember) {
        await removeServerGroupMember(token, group.id, assetId);
      } else {
        await addServerGroupMember(token, group.id, assetId);
      }
      const next = new Set(memberIds);
      if (isMember) next.delete(assetId);
      else next.add(assetId);
      setMemberIds(next);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className={modalStyles.overlay} role="presentation" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        className={modalStyles.dialog}
        style={{ maxHeight: "80vh", overflowY: "auto" }}
      >
        <h3 className={modalStyles.title}>
          {p.manageAssets} — 🗂️ {group.name}
        </h3>
        {memberIds === null && <p className={styles.status}>{t.common.loading}</p>}
        {memberIds !== null && allAssets.length === 0 && <p className={styles.status}>{t.common.noDataAvailable}</p>}
        {memberIds !== null &&
          allAssets.map((asset) => {
            const isMember = memberIds.has(asset.id);
            return (
              <label key={asset.id} className={styles.checkboxRow} style={{ marginTop: 0 }}>
                <input
                  type="checkbox"
                  checked={isMember}
                  disabled={busyId === asset.id}
                  onChange={() => toggle(asset.id, isMember)}
                />
                {asset.hostname || asset.ip_address}
              </label>
            );
          })}
        <div className={styles.actionsCell} style={{ justifyContent: "flex-end" }}>
          <button type="button" className={styles.toolbarButton} onClick={onClose}>
            {t.common.close}
          </button>
        </div>
      </div>
    </div>
  );
}
