"use client";

import { computeAlerts, type AlertSeverity } from "@/lib/alerts";
import { useDashboardData } from "@/lib/DashboardDataProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { timeAgo } from "@/lib/time";
import styles from "./AlertsPanel.module.css";

const SEVERITY_CLASS: Record<AlertSeverity, string> = {
  CRITICAL: "severityCritical",
  WARNING: "severityWarning",
  INFO: "severityInfo",
};

export function AlertsPanel() {
  const { assets, assetsStatus: status } = useDashboardData();
  const { t } = useLocale();

  const alerts = computeAlerts(assets, t.alertMessages);
  const criticalCount = alerts.filter((a) => a.severity === "CRITICAL").length;
  const warningCount = alerts.filter((a) => a.severity === "WARNING").length;
  const infoCount = alerts.filter((a) => a.severity === "INFO").length;

  const severityLabel: Record<AlertSeverity, string> = {
    CRITICAL: t.severity.critical,
    WARNING: t.severity.warning,
    INFO: t.severity.info,
  };

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>{t.dashboard.alertsPanel.title}</h2>
          <p className={styles.subtitle}>{t.dashboard.alertsPanel.subtitle}</p>
        </div>
        {status === "done" && alerts.length > 0 && (
          <div className={styles.overview}>
            <span className={`${styles.overviewCount} ${styles.severityCritical}`}>
              {criticalCount} {t.severity.critical}
            </span>
            <span className={`${styles.overviewCount} ${styles.severityWarning}`}>
              {warningCount} {t.severity.warning}
            </span>
            <span className={`${styles.overviewCount} ${styles.severityInfo}`}>
              {infoCount} {t.severity.info}
            </span>
          </div>
        )}
      </div>

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {status === "error" && (
        <p className={styles.status}>{t.common.unableToLoad}</p>
      )}
      {status === "done" && alerts.length === 0 && (
        <p className={styles.status}>{t.dashboard.alertsPanel.noActiveAlerts}</p>
      )}

      {status === "done" && alerts.length > 0 && (
        <ul className={styles.list}>
          {alerts.map((alert) => (
            <li key={alert.id} className={styles.item}>
              <span
                className={`${styles.badge} ${styles[SEVERITY_CLASS[alert.severity]]}`}
              >
                {severityLabel[alert.severity]}
              </span>
              <span className={styles.message}>{alert.message}</span>
              <span className={styles.time}>{timeAgo(alert.detectedAt, t.timeAgo)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
