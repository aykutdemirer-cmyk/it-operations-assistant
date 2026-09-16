"use client";

import { computeAlerts } from "@/lib/alerts";
import { useDashboardData } from "@/lib/DashboardDataProvider";
import { computeDeviceHealth } from "@/lib/deviceHealth";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./DeviceHealthSummary.module.css";

export function DeviceHealthSummary() {
  const { assets, assetsStatus: status, monitoring } = useDashboardData();
  const { t } = useLocale();

  const alerts = computeAlerts(assets, t.alertMessages, { monitoring });
  const health = computeDeviceHealth(assets, alerts);

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>{t.dashboard.deviceHealth.title}</h2>
        <p className={styles.subtitle}>{t.dashboard.deviceHealth.subtitle}</p>
      </div>

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {status === "error" && (
        <p className={styles.status}>{t.common.unableToLoad}</p>
      )}

      {status === "done" && health.total === 0 && (
        <p className={styles.status}>{t.common.noDataAvailable}.</p>
      )}

      {status === "done" && health.total > 0 && (
        <div className={styles.grid}>
          <span className={`${styles.pill} ${styles.pillHealthy}`}>
            {t.dashboard.deviceHealth.healthy}: {health.healthy}
          </span>
          <span className={`${styles.pill} ${styles.pillWarning}`}>
            {t.dashboard.deviceHealth.warning}: {health.warning}
          </span>
          <span className={`${styles.pill} ${styles.pillCritical}`}>
            {t.dashboard.deviceHealth.critical}: {health.critical}
          </span>
          <span className={`${styles.pill} ${styles.pillUnmonitored}`}>
            {t.dashboard.deviceHealth.unmonitored}: {health.unmonitored}
          </span>
        </div>
      )}

      {status === "done" && health.total > 0 && (
        <p className={styles.hint}>{t.dashboard.deviceHealth.hint}</p>
      )}
    </section>
  );
}
