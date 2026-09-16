"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  createScheduledScan,
  deleteScheduledScan,
  fetchScheduledScans,
  updateScheduledScan,
  type ScheduledScan,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentsList.module.css";
import { ToastStack, useToasts } from "./Toast";

/** Faz 71 — Ayarlar > "Zamanlanmış Taramalar" (ADMIN-only). Kullanıcının
 * açıkça verdiği bir CIDR'ı düzenli aralıklarla YENİDEN tarar — yeni bir
 * aralık asla otomatik keşfedilmez (bkz. `app/discovery/scheduler.py`). */
export function ScheduledScansPanel() {
  const { token } = useAuth();
  const { t } = useLocale();
  const s = t.settings.scheduledScans;

  const [items, setItems] = useState<ScheduledScan[] | null>(null);
  const [cidr, setCidr] = useState("");
  const [intervalHours, setIntervalHours] = useState("24");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const { toasts, push, dismiss } = useToasts();

  async function load() {
    if (!token) return;
    try {
      setItems(await fetchScheduledScans(token));
    } catch {
      setItems([]);
    }
  }

  useEffect(() => {
    Promise.resolve().then(load);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !cidr.trim()) return;
    setBusy(true);
    setFormError(null);
    try {
      await createScheduledScan(token, {
        cidr: cidr.trim(),
        interval_hours: Number(intervalHours) || 24,
        enabled: true,
      });
      setCidr("");
      setIntervalHours("24");
      await load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : s.createError);
    } finally {
      setBusy(false);
    }
  }

  async function handleToggle(item: ScheduledScan) {
    if (!token) return;
    try {
      await updateScheduledScan(token, item.id, { enabled: !item.enabled });
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : s.updateError);
    }
  }

  async function handleDelete(item: ScheduledScan) {
    if (!token) return;
    try {
      await deleteScheduledScan(token, item.id);
      await load();
    } catch (err) {
      push("error", err instanceof ApiError ? err.message : s.deleteError);
    }
  }

  return (
    <section className={styles.card}>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
      <div className={styles.header}>
        <div>
          <h3 className={styles.title}>{s.title}</h3>
          <p className={styles.subtitle}>{s.description}</p>
        </div>
      </div>

      <form onSubmit={handleCreate} className={styles.filterBar}>
        <input
          type="text"
          className={styles.searchInput}
          placeholder={s.cidrPlaceholder}
          value={cidr}
          onChange={(e) => setCidr(e.target.value)}
          aria-label={s.cidrPlaceholder}
        />
        <input
          type="number"
          min={1}
          max={8760}
          className={styles.searchInput}
          style={{ width: 100 }}
          value={intervalHours}
          onChange={(e) => setIntervalHours(e.target.value)}
          aria-label={s.intervalLabel}
        />
        <span className={styles.status}>{s.intervalLabel}</span>
        <button type="submit" className={styles.toolbarButton} disabled={busy || !cidr.trim()}>
          {s.add}
        </button>
      </form>
      {formError && (
        <p className={styles.error} role="alert">
          {formError}
        </p>
      )}

      {items === null && <p className={styles.status}>{t.common.loading}</p>}
      {items !== null && items.length === 0 && <p className={styles.status}>{s.empty}</p>}

      {items !== null && items.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{s.colCidr}</th>
                <th>{s.colInterval}</th>
                <th>{s.colStatus}</th>
                <th>{s.colLastRun}</th>
                <th>{s.colActions}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{item.cidr}</td>
                  <td>{item.interval_hours}h</td>
                  <td>
                    <button
                      type="button"
                      className={styles.actionButton}
                      onClick={() => handleToggle(item)}
                    >
                      {item.enabled ? s.enabled : s.disabled}
                    </button>
                  </td>
                  <td>
                    {item.last_run_at ? (
                      <>
                        <span
                          className={`${styles.badge} ${
                            item.last_run_status === "error" ? styles.badgeRed : styles.badgeGreen
                          }`}
                        >
                          {item.last_run_status === "error" ? s.lastRunError : s.lastRunSuccess}
                        </span>{" "}
                        {new Date(item.last_run_at).toLocaleString()}
                      </>
                    ) : (
                      s.neverRun
                    )}
                  </td>
                  <td className={styles.actionsCell}>
                    <button
                      type="button"
                      className={`${styles.actionButton} ${styles.actionButtonDanger}`}
                      onClick={() => handleDelete(item)}
                    >
                      {s.delete}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
