"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  assignPamTag,
  createPamTag,
  deletePamTag,
  fetchAssets,
  fetchPamTagAssets,
  fetchPamTags,
  unassignPamTag,
  type Asset,
  type PamTag,
  type PamTagAsset,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentsList.module.css";
import { ConfirmModal } from "./ConfirmModal";
import modalStyles from "./EditRuleModal.module.css";
import { ToastStack, useToasts } from "./Toast";

/** Faz 55 — Cihaz Etiketleri (Tags). Bir erişim kuralının TEK bir
 * cihaz YERİNE bir etikete atanabilmesinin yönetim ekranı —
 * `PamRulesPanel.tsx`'in "Cihaz Hedefi Tipi" seçicisinde kullanılır. */
export function PamTagsPanel() {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const [tags, setTags] = useState<PamTag[] | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [error, setError] = useState(false);
  const [newTagName, setNewTagName] = useState("");
  const [saving, setSaving] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<PamTag | null>(null);
  const [managingTag, setManagingTag] = useState<PamTag | null>(null);
  const { toasts, push, dismiss } = useToasts();

  async function load() {
    if (!token) return;
    try {
      const [tagsData, assetsData] = await Promise.all([fetchPamTags(token), fetchAssets()]);
      setTags(tagsData);
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
    if (!token || !newTagName.trim()) return;
    setSaving(true);
    try {
      await createPamTag(token, newTagName.trim());
      setNewTagName("");
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : p.createTagError);
    } finally {
      setSaving(false);
    }
  }

  async function handleConfirmDelete() {
    if (!token || !pendingDelete) return;
    try {
      await deletePamTag(token, pendingDelete.id);
      setPendingDelete(null);
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : p.deleteTagError);
      setPendingDelete(null);
    }
  }

  return (
    <section className={styles.card}>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>{p.tagsTitle}</h2>
          <p className={styles.subtitle}>{p.tagsSubtitle}</p>
        </div>
      </div>

      <form onSubmit={handleCreate} style={{ display: "flex", gap: 8 }}>
        <input
          type="text"
          className={styles.searchInput}
          placeholder={p.newTagPlaceholder}
          value={newTagName}
          onChange={(e) => setNewTagName(e.target.value)}
        />
        <button type="submit" className={styles.toolbarButton} disabled={saving || !newTagName.trim()}>
          {p.create}
        </button>
      </form>

      {error && (
        <p className={styles.error} role="alert">
          {t.common.unableToLoad}
        </p>
      )}
      {!error && tags === null && <p className={styles.status}>{t.common.loading}</p>}
      {!error && tags !== null && tags.length === 0 && <p className={styles.status}>{t.common.noDataAvailable}</p>}

      {!error && tags !== null && tags.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{p.columnName}</th>
                <th>{p.columnActions}</th>
              </tr>
            </thead>
            <tbody>
              {tags.map((tag) => (
                <tr key={tag.id}>
                  <td>
                    <span className={`${styles.badge} ${styles.badgeBlue}`}>🏷️ {tag.name}</span>
                  </td>
                  <td className={styles.actionsCell}>
                    <button type="button" className={styles.actionButton} onClick={() => setManagingTag(tag)}>
                      {p.manageAssets}
                    </button>
                    <button
                      type="button"
                      className={`${styles.actionButton} ${styles.actionButtonDanger}`}
                      onClick={() => setPendingDelete(tag)}
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
          message={p.confirmDeleteTag}
          confirmLabel={p.delete}
          cancelLabel={p.cancel}
          onConfirm={handleConfirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}

      {managingTag && (
        <ManageTagAssetsModal tag={managingTag} allAssets={assets} onClose={() => setManagingTag(null)} />
      )}
    </section>
  );
}

function ManageTagAssetsModal({ tag, allAssets, onClose }: { tag: PamTag; allAssets: Asset[]; onClose: () => void }) {
  const { token } = useAuth();
  const { t } = useLocale();
  const p = t.pam;

  const [assignedIds, setAssignedIds] = useState<Set<string> | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    fetchPamTagAssets(token, tag.id).then((rows: PamTagAsset[]) => setAssignedIds(new Set(rows.map((r) => r.id))));
  }, [token, tag.id]);

  async function toggle(assetId: string, currentlyAssigned: boolean) {
    if (!token || !assignedIds) return;
    setBusyId(assetId);
    try {
      if (currentlyAssigned) {
        await unassignPamTag(token, tag.id, assetId);
      } else {
        await assignPamTag(token, tag.id, assetId);
      }
      const next = new Set(assignedIds);
      if (currentlyAssigned) next.delete(assetId);
      else next.add(assetId);
      setAssignedIds(next);
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
          {p.manageAssets} — 🏷️ {tag.name}
        </h3>
        {assignedIds === null && <p className={styles.status}>{t.common.loading}</p>}
        {assignedIds !== null && allAssets.length === 0 && <p className={styles.status}>{t.common.noDataAvailable}</p>}
        {assignedIds !== null &&
          allAssets.map((asset) => {
            const assigned = assignedIds.has(asset.id);
            return (
              <label key={asset.id} className={styles.checkboxRow} style={{ marginTop: 0 }}>
                <input
                  type="checkbox"
                  checked={assigned}
                  disabled={busyId === asset.id}
                  onChange={() => toggle(asset.id, assigned)}
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
