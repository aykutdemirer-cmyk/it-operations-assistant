"use client";

import { useEffect, useState } from "react";

import { fetchRetentionPolicy, updateRetentionPolicy, type AgentRetentionPolicy } from "@/lib/api";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentsList.module.css";
import { useToasts, ToastStack } from "./Toast";

const _PRESET_DAYS = [7, 14, 30] as const;

/** Lifecycle Management — "İnaktif Agent Otomatik Temizleme" ayarı.
 * `enabled=false` (varsayılan) iken arka plan worker'ı (bkz. `app/
 * agents/scheduler.py`) hiçbir agent'ı arşivlemez — `ENABLE_REMOTE_
 * COMMANDS` ile AYNI opt-in ilkesi. */
export function AgentRetentionPolicyPanel() {
  const { t } = useLocale();
  const p = t.agents.retentionPolicy;

  const [policy, setPolicy] = useState<AgentRetentionPolicy | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [saving, setSaving] = useState(false);
  const { toasts, push, dismiss } = useToasts();

  useEffect(() => {
    fetchRetentionPolicy()
      .then(setPolicy)
      .catch(() => setLoadError(true));
  }, []);

  async function save(next: AgentRetentionPolicy) {
    setSaving(true);
    try {
      const saved = await updateRetentionPolicy(next);
      setPolicy(saved);
      push("success", p.saveSuccess);
    } catch {
      push("error", p.saveError);
    } finally {
      setSaving(false);
    }
  }

  if (loadError) {
    return (
      <section className={styles.retentionPanel}>
        <p className={styles.error} role="alert">
          {p.loadError}
        </p>
      </section>
    );
  }

  if (!policy) {
    return (
      <section className={styles.retentionPanel}>
        <p className={styles.status}>{t.common.loading}</p>
      </section>
    );
  }

  return (
    <section className={styles.retentionPanel}>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
      <div>
        <h3 className={styles.title}>{p.title}</h3>
        <p className={styles.subtitle}>{p.description}</p>
      </div>
      <div className={styles.retentionRow}>
        <label className={styles.checkboxRow} style={{ marginTop: 0 }}>
          <input
            type="checkbox"
            checked={policy.enabled}
            disabled={saving}
            onChange={(e) => save({ ...policy, enabled: e.target.checked })}
          />
          {p.enabledLabel}
        </label>
      </div>
      <div className={styles.retentionRow}>
        <span>{p.daysLabel}:</span>
        {_PRESET_DAYS.map((days) => (
          <button
            key={days}
            type="button"
            className={`${styles.presetButton} ${policy.retention_days === days ? styles.presetButtonActive : ""}`}
            disabled={saving}
            onClick={() => save({ ...policy, retention_days: days })}
          >
            {p.presets[String(days) as "7" | "14" | "30"]}
          </button>
        ))}
        <input
          className={styles.retentionDaysInput}
          type="number"
          min={1}
          max={3650}
          value={policy.retention_days}
          disabled={saving}
          onChange={(e) => setPolicy({ ...policy, retention_days: Number(e.target.value) || 1 })}
          aria-label={p.daysLabel}
        />
        <button
          type="button"
          className={styles.toolbarButton}
          disabled={saving}
          onClick={() => save(policy)}
        >
          {p.save}
        </button>
      </div>
    </section>
  );
}
