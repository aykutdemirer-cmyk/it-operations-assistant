"use client";

import type { Asset } from "@/lib/api";
import { useDashboardData } from "@/lib/DashboardDataProvider";
import { computeInfrastructureHealth } from "@/lib/health";
import { aggregateOpenPorts } from "@/lib/portRisk";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./DashboardSummary.module.css";

function mostRecentLastSeen(assets: Asset[]): string | null {
  return assets.reduce<string | null>((latest, asset) => {
    if (!latest) return asset.last_seen;
    return new Date(asset.last_seen) > new Date(latest) ? asset.last_seen : latest;
  }, null);
}

function healthAccent(percent: number | null): "up" | "warning" | "down" | "neutral" {
  if (percent == null) return "neutral";
  if (percent >= 90) return "up";
  if (percent >= 70) return "warning";
  return "down";
}

/** Faz 36 — Dashboard sadeleştirmesi: 9 dağınık küçük kart yerine 4 ana
 * KPI kartı. "Son Görülme" artık devasa bir kart değil, sağ üst köşede
 * pasif bir metin (bkz. `lastScan`). */
export function DashboardSummary() {
  const { assets, assetsStatus } = useDashboardData();
  const { t } = useLocale();
  const s = t.dashboard.summary;
  const showValues = assetsStatus === "done";

  const onlineCount = assets.filter((a) => a.status === "up").length;
  const offlineCount = assets.filter((a) => a.status === "down").length;
  const unknownCount = assets.filter((a) => a.device_type === "unknown").length;
  const totalOpenPorts = assets.reduce((sum, asset) => sum + asset.open_ports.length, 0);
  const highRiskPorts = aggregateOpenPorts(assets).filter((p) => p.risk === "HIGH");
  const highRiskPortCount = highRiskPorts.reduce((sum, p) => sum + p.deviceCount, 0);
  const health = computeInfrastructureHealth(assets);
  const lastSeen = mostRecentLastSeen(assets);
  const accent = healthAccent(health.availabilityPercent);

  return (
    <div>
      <div className={styles.topRow}>
        <span className={styles.lastScan}>
          {lastSeen ? `${s.lastSeen}: ${new Date(lastSeen).toLocaleString()}` : `${s.lastSeen}: -`}
        </span>
      </div>

      <section className={styles.grid} aria-label={t.common.dashboardSummaryAriaLabel}>
        <div className={`${styles.card} ${styles["accent-neutral"]}`}>
          <div className={styles.cardTop}>
            <span className={styles.icon} aria-hidden="true">🖥️</span>
            <span className={styles.label}>{s.totalAssets}</span>
          </div>
          <span className={styles.value}>{showValues ? assets.length : "–"}</span>
          <div className={styles.miniBadges}>
            <span className={`${styles.miniBadge} ${styles.miniBadgeUp}`}>
              🟢 {showValues ? onlineCount : "–"} {s.online}
            </span>
            <span className={`${styles.miniBadge} ${styles.miniBadgeDown}`}>
              🔴 {showValues ? offlineCount : "–"} {s.offline}
            </span>
          </div>
        </div>

        <div className={`${styles.card} ${styles["accent-violet"]}`}>
          <div className={styles.cardTop}>
            <span className={styles.icon} aria-hidden="true">🔓</span>
            <span className={styles.label}>{s.highRiskPortsCard}</span>
          </div>
          <span className={styles.value}>{showValues ? highRiskPortCount : "–"}</span>
          <span className={styles.description}>
            {showValues ? `${totalOpenPorts} ${s.openPorts.toLowerCase()}` : s.highRiskPortsDesc}
          </span>
        </div>

        <div className={`${styles.card} ${styles["accent-neutral"]}`}>
          <div className={styles.cardTop}>
            <span className={styles.icon} aria-hidden="true">❓</span>
            <span className={styles.label}>{s.unknown}</span>
          </div>
          <span className={styles.value}>{showValues ? unknownCount : "–"}</span>
          <span className={styles.description}>{s.unknownDesc}</span>
        </div>

        <div className={`${styles.card} ${styles[`accent-${accent}`]}`}>
          <div className={styles.cardTop}>
            <span className={styles.icon} aria-hidden="true">🛡️</span>
            <span className={styles.label}>{s.healthScoreCard}</span>
          </div>
          <span className={styles.value}>
            {showValues && health.availabilityPercent != null ? `${health.availabilityPercent}%` : "–"}
          </span>
          <span className={styles.description}>{s.healthScoreDesc}</span>
        </div>
      </section>
    </div>
  );
}
