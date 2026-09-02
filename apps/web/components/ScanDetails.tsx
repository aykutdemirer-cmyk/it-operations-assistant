"use client";

import { useEffect } from "react";

import type { Scan } from "@/lib/api";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./ScanDetails.module.css";

function formatTimestamp(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : "-";
}

function formatDuration(ms: number | null): string {
  if (ms == null) return "-";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

type Props = {
  scan: Scan;
  onClose: () => void;
};

export function ScanDetails({ scan, onClose }: Props) {
  const { t } = useLocale();

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <aside
        className={styles.panel}
        onClick={(event) => event.stopPropagation()}
        aria-label={t.scans.details.ariaLabel}
      >
        <div className={styles.panelHeader}>
          <h3 className={styles.panelTitle}>{scan.cidr}</h3>
          <button
            className={styles.closeButton}
            onClick={onClose}
            aria-label={t.scans.details.closeButton}
          >
            ✕
          </button>
        </div>

        <dl className={styles.fields}>
          <div className={styles.field}>
            <dt>{t.scans.details.scanId}</dt>
            <dd className={styles.mono}>{scan.id}</dd>
          </div>
          <div className={styles.field}>
            <dt>{t.scans.columns.status}</dt>
            <dd>{t.scans.statusLabels[scan.status]}</dd>
          </div>
          <div className={styles.field}>
            <dt>{t.scans.columns.started}</dt>
            <dd>{formatTimestamp(scan.started_at)}</dd>
          </div>
          <div className={styles.field}>
            <dt>{t.scans.columns.completed}</dt>
            <dd>{formatTimestamp(scan.completed_at)}</dd>
          </div>
          <div className={styles.field}>
            <dt>{t.scans.columns.duration}</dt>
            <dd>{formatDuration(scan.duration_ms)}</dd>
          </div>
          <div className={styles.field}>
            <dt>{t.scans.columns.hostsScanned}</dt>
            <dd>{scan.hosts_scanned}</dd>
          </div>
          <div className={styles.field}>
            <dt>{t.scans.columns.hostsDiscovered}</dt>
            <dd>{scan.hosts_discovered}</dd>
          </div>
          <div className={styles.field}>
            <dt>{t.scans.columns.openPorts}</dt>
            <dd>{scan.open_ports}</dd>
          </div>
        </dl>
      </aside>
    </div>
  );
}
