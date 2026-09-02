"use client";

import { useDashboardData } from "@/lib/DashboardDataProvider";
import { computeInfrastructureHealth } from "@/lib/health";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./InfrastructureHealth.module.css";

function availabilityAccent(percent: number | null): string {
  if (percent == null) return "neutral";
  if (percent >= 90) return "up";
  if (percent >= 70) return "warning";
  return "down";
}

export function InfrastructureHealth() {
  const { assets, assetsStatus: status } = useDashboardData();
  const { t } = useLocale();

  const health = computeInfrastructureHealth(assets);
  const accent = availabilityAccent(health.availabilityPercent);

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>{t.dashboard.health.title}</h2>
        <p className={styles.subtitle}>{t.dashboard.health.subtitle}</p>
      </div>

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {status === "error" && (
        <p className={styles.status}>{t.common.unableToLoad}</p>
      )}

      {status === "done" && health.total === 0 && (
        <p className={styles.status}>{t.common.noDataAvailable}.</p>
      )}

      {status === "done" && health.total > 0 && (
        <div className={styles.body}>
          <div
            className={styles.donut}
            role="img"
            aria-label={`${t.dashboard.health.overallAvailability}: ${health.availabilityPercent}%`}
            style={{
              background: `conic-gradient(var(--status-up) 0% ${health.onlinePercent ?? 0}%, var(--status-down) ${health.onlinePercent ?? 0}% ${
                (health.onlinePercent ?? 0) + (health.offlinePercent ?? 0)
              }%, var(--status-unknown) ${(health.onlinePercent ?? 0) + (health.offlinePercent ?? 0)}% 100%)`,
            }}
          >
            <div className={styles.donutHole}>
              <span className={`${styles.availabilityValue} ${styles[`accent-${accent}`]}`}>
                {health.availabilityPercent}%
              </span>
              <span className={styles.availabilityLabel}>{t.dashboard.health.overallAvailability}</span>
            </div>
          </div>

          <div className={styles.breakdown}>
            <div className={styles.legend}>
              <span className={styles.legendItem}>
                <span className={`${styles.dot} ${styles.dotUp}`} aria-hidden="true" />
                {t.dashboard.health.online} {health.onlinePercent ?? 0}% ({health.online})
              </span>
              <span className={styles.legendItem}>
                <span className={`${styles.dot} ${styles.dotDown}`} aria-hidden="true" />
                {t.dashboard.health.offline} {health.offlinePercent ?? 0}% ({health.offline})
              </span>
              <span className={styles.legendItem}>
                <span
                  className={`${styles.dot} ${styles.dotUnknown}`}
                  aria-hidden="true"
                />
                {t.dashboard.health.unknown} {health.unknownPercent ?? 0}% ({health.unknown})
              </span>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
