"use client";

import { useMemo, useState } from "react";

import { computeAlerts, type AlertSeverity } from "@/lib/alerts";
import { useDashboardData } from "@/lib/DashboardDataProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { timeAgo } from "@/lib/time";
import styles from "./AlertsList.module.css";

type SeverityFilter = "all" | AlertSeverity;

const SEVERITY_CLASS: Record<AlertSeverity, string> = {
  CRITICAL: "severityCritical",
  WARNING: "severityWarning",
  INFO: "severityInfo",
};

/**
 * `/alerts` sayfası — dashboard'daki kompakt `AlertsPanel` widget'ından
 * farklı olarak tam liste + filtre + arama sağlar. Uydurma alert yok:
 * `computeAlerts` aynı, gerçek `assets` verisinden türetiliyor (bkz.
 * `lib/alerts.ts`).
 */
export function AlertsList() {
  const { assets, assetsStatus: status, monitoring } = useDashboardData();
  const { t } = useLocale();
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [search, setSearch] = useState("");

  const alerts = computeAlerts(assets, t.alertMessages, { monitoring });

  const severityLabel: Record<AlertSeverity, string> = {
    CRITICAL: t.severity.critical,
    WARNING: t.severity.warning,
    INFO: t.severity.info,
  };

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return alerts.filter((alert) => {
      if (severityFilter !== "all" && alert.severity !== severityFilter) {
        return false;
      }
      if (query) {
        const haystack = `${alert.assetLabel} ${alert.message}`.toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      return true;
    });
  }, [alerts, severityFilter, search]);

  const filterOptions: { key: SeverityFilter; label: string }[] = [
    { key: "all", label: t.alerts.filterAll },
    { key: "CRITICAL", label: t.alerts.filterCritical },
    { key: "WARNING", label: t.alerts.filterWarning },
    { key: "INFO", label: t.alerts.filterInfo },
  ];

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>{t.alerts.title}</h2>
        <p className={styles.subtitle}>{t.alerts.subtitle}</p>
      </div>

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {status === "error" && <p className={styles.status}>{t.common.unableToLoad}</p>}

      {status === "done" && (
        <>
          {alerts.length > 0 && (
            <div className={styles.controls}>
              <input
                className={styles.searchInput}
                type="text"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t.alerts.searchPlaceholder}
                aria-label={t.alerts.searchAriaLabel}
              />
              <div className={styles.filterGroup} role="group">
                {filterOptions.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    className={`${styles.filterButton} ${
                      severityFilter === option.key ? styles.filterButtonActive : ""
                    }`}
                    onClick={() => setSeverityFilter(option.key)}
                    aria-pressed={severityFilter === option.key}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {alerts.length === 0 && (
            <p className={styles.status}>{t.alerts.noAlerts}</p>
          )}

          {alerts.length > 0 && filtered.length === 0 && (
            <p className={styles.status}>{t.alerts.noMatchFilters}</p>
          )}

          {filtered.length > 0 && (
            <ul className={styles.list}>
              {filtered.map((alert) => (
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
        </>
      )}
    </section>
  );
}
