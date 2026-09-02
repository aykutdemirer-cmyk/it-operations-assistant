"use client";

import { buildActivityFeed, type ActivityType } from "@/lib/activity";
import { useDashboardData } from "@/lib/DashboardDataProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { timeAgo } from "@/lib/time";
import styles from "./RecentActivity.module.css";

const MAX_ITEMS = 8;

const ICONS: Record<ActivityType, string> = {
  asset_discovered: "🆕",
  asset_updated: "🔄",
  scan_completed: "✅",
  scan_failed: "❌",
};

export function RecentActivity() {
  const { assets, assetsStatus, scans, scansStatus } = useDashboardData();
  const { t } = useLocale();

  const status =
    assetsStatus === "error" || scansStatus === "error"
      ? "error"
      : assetsStatus === "loading" || scansStatus === "loading"
        ? "loading"
        : "done";
  const items = buildActivityFeed(assets, scans).slice(0, MAX_ITEMS);
  const a = t.dashboard.recentActivity;
  const label: Record<ActivityType, string> = {
    asset_discovered: a.assetDiscovered,
    asset_updated: a.assetUpdated,
    scan_completed: a.scanCompleted,
    scan_failed: a.scanFailed,
  };

  return (
    <section className={styles.card}>
      <h2 className={styles.title}>{a.title}</h2>
      <p className={styles.subtitle}>{a.subtitle}</p>

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {status === "error" && (
        <p className={styles.status}>{t.common.unableToLoad}</p>
      )}
      {status === "done" && items.length === 0 && (
        <p className={styles.status}>{a.noActivity}</p>
      )}

      {status === "done" && items.length > 0 && (
        <ul className={styles.list}>
          {items.map((item) => (
            <li className={styles.item} key={item.id}>
              <span className={styles.icon} aria-hidden="true">
                {ICONS[item.type]}
              </span>
              <span className={styles.itemText}>
                <span className={styles.itemName}>
                  {label[item.type]} · {item.detail}
                </span>
                <span className={styles.itemMeta}>{timeAgo(item.timestamp, t.timeAgo)}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
