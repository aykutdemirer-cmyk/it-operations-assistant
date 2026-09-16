"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  createTicketCategory,
  createTicketDepartment,
  deleteTicketCategory,
  deleteTicketDepartment,
  fetchSlaPolicy,
  fetchTicketCategories,
  fetchTicketDepartments,
  updateSlaPolicy,
  type SlaPolicy,
  type TicketPriority,
  type TicketTaxonomyItem,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentsList.module.css";
import editModalStyles from "./EditRuleModal.module.css";

type Kind = "departments" | "categories";
type Tab = Kind | "sla";
const SLA_PRIORITIES: TicketPriority[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

/** Faz 63 — Admin-only "Bilet Ayarları" modalı: iki panel (Departman /
 * Kategori). "Silme" backend'de soft-delete (`is_active=false`) — mevcut
 * biletlerin FK'si korunur. Aynı adı yeniden eklemek pasif satırı geri
 * getirir. */
export function TicketSettingsModal({ onClose, onChanged }: { onClose: () => void; onChanged: () => void }) {
  const { token } = useAuth();
  const { t } = useLocale();
  const k = t.tickets;
  const [tab, setTab] = useState<Tab>("departments");

  return (
    <div className={editModalStyles.overlay} role="presentation" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={k.settingsTitle}
        className={editModalStyles.dialog}
        style={{ width: "min(640px, 94vw)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className={editModalStyles.title}>{k.settingsTitle}</h3>

        <div className={styles.filterBar} role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "departments"}
            className={`${styles.actionButton} ${tab === "departments" ? styles.toolbarButton : ""}`}
            onClick={() => setTab("departments")}
          >
            {k.tabDepartments}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "categories"}
            className={`${styles.actionButton} ${tab === "categories" ? styles.toolbarButton : ""}`}
            onClick={() => setTab("categories")}
          >
            {k.tabCategories}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "sla"}
            className={`${styles.actionButton} ${tab === "sla" ? styles.toolbarButton : ""}`}
            onClick={() => setTab("sla")}
          >
            {k.tabSla}
          </button>
        </div>

        {tab === "departments" && (
          <TaxonomyPanel
            kind="departments"
            fetchAll={() => fetchTicketDepartments(token!, true)}
            add={(name) => createTicketDepartment(token!, name)}
            remove={(id) => deleteTicketDepartment(token!, id)}
            placeholder={k.newDepartmentPlaceholder}
            onChanged={onChanged}
          />
        )}
        {tab === "categories" && (
          <TaxonomyPanel
            kind="categories"
            fetchAll={() => fetchTicketCategories(token!, true)}
            add={(name) => createTicketCategory(token!, name)}
            remove={(id) => deleteTicketCategory(token!, id)}
            placeholder={k.newCategoryPlaceholder}
            onChanged={onChanged}
          />
        )}
        {tab === "sla" && <SlaPanel token={token!} />}

        <div className={editModalStyles.actions}>
          <button type="button" className={styles.actionButton} onClick={onClose}>
            {k.cancel}
          </button>
        </div>
      </div>
    </div>
  );
}

function SlaPanel({ token }: { token: string }) {
  const { t } = useLocale();
  const k = t.tickets;
  const [policy, setPolicy] = useState<SlaPolicy | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    Promise.resolve().then(async () => {
      try {
        setPolicy(await fetchSlaPolicy(token));
      } catch {
        setPolicy(null);
      }
    });
  }, [token]);

  async function handleSave(priority: TicketPriority) {
    const raw = draft[priority];
    const hours = Number(raw);
    if (!raw || !Number.isFinite(hours) || hours < 1) return;
    setBusy(priority);
    setErrorMessage(null);
    try {
      const updated = await updateSlaPolicy(token, priority, Math.round(hours));
      setPolicy(updated);
      setDraft((d) => {
        const next = { ...d };
        delete next[priority];
        return next;
      });
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : k.slaSaveError);
    } finally {
      setBusy(null);
    }
  }

  if (policy === null) return <p className={styles.status}>{t.common.loading}</p>;

  return (
    <div>
      <p className={styles.status}>{k.slaHint}</p>
      {errorMessage && (
        <p className={styles.error} role="alert">
          {errorMessage}
        </p>
      )}
      <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: 6, margin: "8px 0" }}>
        {SLA_PRIORITIES.map((p) => {
          const current = policy[p];
          const value = draft[p] ?? String(current);
          return (
            <li
              key={p}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
                padding: "6px 10px",
                background: "var(--surface-raised)",
                borderRadius: "var(--radius-md)",
              }}
            >
              <span>{k[`priority${p}`]}</span>
              <span className={styles.filterBar}>
                <input
                  type="number"
                  min={1}
                  max={8760}
                  className={styles.searchInput}
                  style={{ width: 90 }}
                  aria-label={`${k[`priority${p}`]} — ${k.slaHoursLabel}`}
                  value={value}
                  onChange={(e) => setDraft((d) => ({ ...d, [p]: e.target.value }))}
                />
                <span className={styles.status}>{k.slaHoursLabel}</span>
                <button
                  type="button"
                  className={styles.toolbarButton}
                  disabled={busy === p || value === String(current)}
                  onClick={() => handleSave(p)}
                >
                  {k.add}
                </button>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function TaxonomyPanel({
  kind,
  fetchAll,
  add,
  remove,
  placeholder,
  onChanged,
}: {
  kind: Kind;
  fetchAll: () => Promise<TicketTaxonomyItem[]>;
  add: (name: string) => Promise<TicketTaxonomyItem>;
  remove: (id: string) => Promise<void>;
  placeholder: string;
  onChanged: () => void;
}) {
  const { t } = useLocale();
  const k = t.tickets;
  const [items, setItems] = useState<TicketTaxonomyItem[] | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function reload() {
    try {
      setItems(await fetchAll());
    } catch {
      setItems([]);
    }
  }

  useEffect(() => {
    Promise.resolve().then(reload);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setErrorMessage(null);
    try {
      await add(name.trim());
      setName("");
      await reload();
      onChanged();
    } catch (err) {
      setErrorMessage(
        err instanceof ApiError ? (err.status === 409 ? k.taxonomyExists : err.message) : k.taxonomyAddError,
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(id: string) {
    setBusy(true);
    try {
      await remove(id);
      await reload();
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {errorMessage && (
        <p className={styles.error} role="alert">
          {errorMessage}
        </p>
      )}
      <form onSubmit={handleAdd} className={styles.filterBar}>
        <input
          type="text"
          className={styles.searchInput}
          placeholder={placeholder}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button type="submit" className={styles.toolbarButton} disabled={busy || !name.trim()}>
          {k.add}
        </button>
      </form>

      {items === null && <p className={styles.status}>{t.common.loading}</p>}
      {items !== null && (
        <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: 6, margin: "8px 0" }}>
          {items.map((item) => (
            <li
              key={item.id}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
                padding: "6px 10px",
                background: "var(--surface-raised)",
                borderRadius: "var(--radius-md)",
                opacity: item.is_active ? 1 : 0.5,
              }}
            >
              <span>
                {item.name} {!item.is_active && <em className={styles.status}>{k.inactive}</em>}
              </span>
              {item.is_active && (
                <button
                  type="button"
                  className={`${styles.actionButton} ${styles.actionButtonDanger}`}
                  disabled={busy}
                  onClick={() => handleRemove(item.id)}
                >
                  {k.deactivate}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
