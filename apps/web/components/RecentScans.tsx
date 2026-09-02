"use client";

import { useState } from "react";

import type { Scan, ScanStatus } from "@/lib/api";
import { useDashboardData } from "@/lib/DashboardDataProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { ScanDetails } from "@/components/ScanDetails";
import styles from "./RecentScans.module.css";

const DEFAULT_MAX_ITEMS = 5;

const STATUS_CLASS: Record<ScanStatus, string> = {
  completed: "statusCompleted",
  running: "statusRunning",
  failed: "statusFailed",
};

function formatTimestamp(isoTimestamp: string | null): string {
  return isoTimestamp ? new Date(isoTimestamp).toLocaleString() : "-";
}

function formatDuration(ms: number | null): string {
  if (ms == null) return "-";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

type Props = {
  /** Gösterilecek en fazla tarama sayısı. Belirtilmezse dashboard
   * widget'ı davranışı (en fazla 5) korunur; `/scans` sayfası tüm
   * geçmişi göstermek için daha büyük bir değer geçebilir. */
  limit?: number;
};

export function RecentScans({ limit = DEFAULT_MAX_ITEMS }: Props) {
  const { scans, scansStatus: status } = useDashboardData();
  const [selectedScan, setSelectedScan] = useState<Scan | null>(null);
  const { t } = useLocale();

  const recent = scans.slice(0, limit);

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>{t.scans.title}</h2>
          <p className={styles.subtitle}>{t.scans.subtitle}</p>
        </div>
      </div>

      {status === "loading" && <p className={styles.status}>{t.scans.loading}</p>}
      {status === "error" && <p className={styles.error}>{t.scans.error}</p>}
      {status === "done" && recent.length === 0 && (
        <p className={styles.status}>{t.scans.noScans}</p>
      )}

      {status === "done" && recent.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{t.scans.columns.status}</th>
                <th>{t.scans.columns.cidr}</th>
                <th>{t.scans.columns.started}</th>
                <th>{t.scans.columns.completed}</th>
                <th>{t.scans.columns.duration}</th>
                <th>{t.scans.columns.hostsScanned}</th>
                <th>{t.scans.columns.hostsDiscovered}</th>
                <th>{t.scans.columns.openPorts}</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((scan) => (
                <tr
                  className={styles.row}
                  key={scan.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedScan(scan)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedScan(scan);
                    }
                  }}
                >
                  <td>
                    <span
                      className={`${styles.badge} ${styles[STATUS_CLASS[scan.status]]}`}
                    >
                      {t.scans.statusLabels[scan.status]}
                    </span>
                  </td>
                  <td className={styles.mono}>{scan.cidr}</td>
                  <td>{formatTimestamp(scan.started_at)}</td>
                  <td>{formatTimestamp(scan.completed_at)}</td>
                  <td>{formatDuration(scan.duration_ms)}</td>
                  <td>{scan.hosts_scanned}</td>
                  <td>{scan.hosts_discovered}</td>
                  <td>{scan.open_ports}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedScan && (
        <ScanDetails scan={selectedScan} onClose={() => setSelectedScan(null)} />
      )}
    </section>
  );
}
