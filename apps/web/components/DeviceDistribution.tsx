"use client";

import type { Asset } from "@/lib/api";
import { useDashboardData } from "@/lib/DashboardDataProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import type { translations } from "@/lib/i18n/translations";
import styles from "./DeviceDistribution.module.css";

type Dict = (typeof translations)["tr"];

type DeviceCount = {
  deviceType: string;
  label: string;
  count: number;
  percent: number;
};

function deviceTypeLabel(deviceType: string, t: Dict): string {
  return (
    t.deviceType[deviceType as keyof Dict["deviceType"]] ??
    deviceType
      .split("_")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ")
  );
}

function computeDistribution(assets: Asset[], t: Dict): DeviceCount[] {
  const total = assets.length;
  if (total === 0) return [];

  const counts = new Map<string, number>();
  for (const asset of assets) {
    counts.set(asset.device_type, (counts.get(asset.device_type) ?? 0) + 1);
  }

  return Array.from(counts.entries())
    .map(([deviceType, count]) => ({
      deviceType,
      label: deviceTypeLabel(deviceType, t),
      count,
      percent: Math.round((count / total) * 1000) / 10,
    }))
    .sort((a, b) => b.count - a.count);
}

export function DeviceDistribution() {
  const { assets, assetsStatus: status } = useDashboardData();
  const { t } = useLocale();

  const distribution = computeDistribution(assets, t);
  const d = t.dashboard.deviceDistribution;

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>{d.title}</h2>
        <p className={styles.subtitle}>{d.subtitle}</p>
      </div>

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {status === "error" && (
        <p className={styles.status}>{t.common.unableToLoad}</p>
      )}
      {status === "done" && distribution.length === 0 && (
        <p className={styles.status}>{d.noAssets}</p>
      )}

      {status === "done" && distribution.length > 0 && (
        <div className={styles.chart}>
          {distribution.map((entry) => (
            <div className={styles.row} key={entry.deviceType}>
              <span className={styles.rowLabel}>{entry.label}</span>
              <div className={styles.barTrack}>
                <div
                  className={styles.barFill}
                  style={{ width: `${entry.percent}%` }}
                />
              </div>
              <span className={styles.rowCount}>
                {entry.count} ({entry.percent}%)
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
