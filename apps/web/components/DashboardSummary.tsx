"use client";

import Link from "next/link";

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
  const { assets, assetsStatus, refetchAssets } = useDashboardData();
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
        <button
          type="button"
          className={styles.refreshButton}
          onClick={() => refetchAssets()}
          disabled={assetsStatus === "loading"}
        >
          {assetsStatus === "loading" ? t.common.refreshing : t.common.refresh}
        </button>
      </div>

      {/* Faz: her KPI kartı artık `/assets`'e filtrelenmiş bir hızlı
          bağlantı (kullanıcı isteği) + hover tooltip (`title`) taşıyor —
          gerçek bir filtre sonucuna gider, uydurma bir sayım DEĞİL. */}
      <section className={styles.grid} aria-label={t.common.dashboardSummaryAriaLabel}>
        <Link
          href="/assets"
          className={`${styles.card} ${styles["accent-neutral"]}`}
          title={`${s.totalAssetsDesc} — ${s.clickHint}`}
        >
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
        </Link>

        <Link
          href="/assets?highRisk=1"
          className={`${styles.card} ${styles["accent-violet"]}`}
          title={`${s.highRiskPortsDesc} — ${s.clickHint}`}
        >
          <div className={styles.cardTop}>
            <span className={styles.icon} aria-hidden="true">🔓</span>
            <span className={styles.label}>{s.highRiskPortsCard}</span>
          </div>
          <span className={styles.value}>{showValues ? highRiskPortCount : "–"}</span>
          <span className={styles.description}>
            {showValues ? `${totalOpenPorts} ${s.openPorts.toLowerCase()}` : s.highRiskPortsDesc}
          </span>
        </Link>

        <Link
          href="/assets?deviceType=unknown"
          className={`${styles.card} ${styles["accent-neutral"]}`}
          title={`${s.unknownDesc} — ${s.clickHint}`}
        >
          <div className={styles.cardTop}>
            <span className={styles.icon} aria-hidden="true">❓</span>
            <span className={styles.label}>{s.unknown}</span>
          </div>
          <span className={styles.value}>{showValues ? unknownCount : "–"}</span>
          <span className={styles.description}>{s.unknownDesc}</span>
        </Link>

        <Link
          href="/assets?status=down"
          className={`${styles.card} ${styles[`accent-${accent}`]}`}
          title={`${s.healthScoreDesc} — ${s.clickHint}`}
        >
          <div className={styles.cardTop}>
            <span className={styles.icon} aria-hidden="true">🛡️</span>
            <span className={styles.label}>{s.healthScoreCard}</span>
          </div>
          <span className={styles.value}>
            {showValues && health.availabilityPercent != null ? `${health.availabilityPercent}%` : "–"}
          </span>
          <span className={styles.description}>{s.healthScoreDesc}</span>
        </Link>
      </section>
    </div>
  );
}
