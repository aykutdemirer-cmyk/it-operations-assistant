"use client";

import type { VCenterSummary } from "@/lib/api";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./VCenterPanel.module.css";

function fillClass(styles: Record<string, string>, usedPercent: number): string {
  // Faz 73 — kullanıcının istediği eşikler: <%70 normal, %70-85 uyarı, >%85 tehlike.
  if (usedPercent >= 85) return `${styles.progressFill} ${styles.progressFillDanger}`;
  if (usedPercent >= 70) return `${styles.progressFill} ${styles.progressFillWarning}`;
  return styles.progressFill;
}

/** Faz 72 — Üst KPI kartları + datastore doluluk çubukları. Tüm
 * değerler `VCenterSummary`'den — hiçbiri sabit/uydurma DEĞİL. */
export function VCenterSummaryCards({ summary }: { summary: VCenterSummary }) {
  const { t } = useLocale();
  const v = t.vcenter;

  return (
    <>
      <div className={styles.kpiGrid}>
        <div className={styles.kpiCard}>
          <span className={styles.kpiValue}>{summary.total_vms}</span>
          <span className={styles.kpiLabel}>{v.kpi.totalVms}</span>
        </div>
        <div className={styles.kpiCard}>
          <span className={styles.kpiValue}>{summary.powered_on_vms}</span>
          <span className={styles.kpiLabel}>{v.kpi.poweredOnVms}</span>
        </div>
        <div className={styles.kpiCard}>
          <span className={styles.kpiValue}>{summary.total_hosts}</span>
          <span className={styles.kpiLabel}>{v.kpi.totalHosts}</span>
        </div>
        <div className={styles.kpiCard}>
          <span className={styles.kpiValue}>{summary.total_vcpu_allocated}</span>
          <span className={styles.kpiLabel}>{v.kpi.totalVcpu}</span>
        </div>
        <div className={styles.kpiCard}>
          <span className={styles.kpiValue}>{summary.total_memory_gb_allocated.toFixed(1)} GB</span>
          <span className={styles.kpiLabel}>{v.kpi.totalMemory}</span>
        </div>
      </div>

      {summary.datastores.length > 0 && (
        <div className={styles.datastoreCard}>
          <span className={styles.kpiLabel}>{v.kpi.datastoreUsage}</span>
          {summary.datastores.map((ds) => {
            const used = ds.capacity_gb > 0 ? ((ds.capacity_gb - ds.free_gb) / ds.capacity_gb) * 100 : 0;
            return (
              <div key={ds.id} className={styles.datastoreRow}>
                <span className={styles.datastoreLabel}>
                  <span>{ds.name}</span>
                  <span>
                    {(ds.capacity_gb - ds.free_gb).toFixed(0)} / {ds.capacity_gb.toFixed(0)} GB ({used.toFixed(0)}%)
                  </span>
                </span>
                <div className={styles.progressTrack}>
                  <div className={fillClass(styles, used)} style={{ width: `${Math.min(100, used)}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
