"use client";

import { useEffect, useState } from "react";

import { fetchSnmpProfiles } from "@/lib/api";
import { useDashboardData } from "@/lib/DashboardDataProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { computeMonitoringCoverage } from "@/lib/monitoringCoverage";
import styles from "./MonitoringCoverage.module.css";

export function MonitoringCoverage() {
  const { assets, assetsStatus: status } = useDashboardData();
  const { t } = useLocale();

  // `snmpEnabled` gerçek `asset_snmp_profiles` ilişkisinden gelir (Faz
  // 29.5) — her profilin `assigned_asset_count`'unun toplamı. Ağır bir
  // grafik değil, yalnızca tek bir ek `GET /api/snmp/profiles` çağrısı.
  const [snmpAssignedCount, setSnmpAssignedCount] = useState(0);

  useEffect(() => {
    fetchSnmpProfiles()
      .then((profiles) => {
        setSnmpAssignedCount(profiles.reduce((sum, p) => sum + p.assigned_asset_count, 0));
      })
      .catch(() => {
        // sessizce yut — bu widget zaten asset durumuna göre render
        // ediliyor; profil listesi alınamazsa snmpEnabled 0 kalır
        // (uydurulmuş bir sayı yerine dürüst bir alt sınır).
      });
  }, []);

  const coverage = computeMonitoringCoverage(assets, snmpAssignedCount);
  const c = t.dashboard.monitoringCoverage;

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>{c.title}</h2>
        <p className={styles.subtitle}>{c.subtitle}</p>
      </div>

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {status === "error" && (
        <p className={styles.status}>{t.common.unableToLoad}</p>
      )}

      {status === "done" && coverage.total === 0 && (
        <p className={styles.status}>{t.common.noDataAvailable}.</p>
      )}

      {status === "done" && coverage.total > 0 && (
        <dl className={styles.rows}>
          <div className={styles.row}>
            <dt>{c.totalAssets}</dt>
            <dd>{coverage.total}</dd>
          </div>
          <div className={styles.row}>
            <dt>{c.snmpEnabled}</dt>
            <dd>{coverage.snmpEnabled}</dd>
          </div>
          <div className={styles.row}>
            <dt>{c.snmpDisabled}</dt>
            <dd>{coverage.snmpDisabled}</dd>
          </div>
          <div className={styles.row}>
            <dt>{c.unreachable}</dt>
            <dd>{coverage.unreachable}</dd>
          </div>
        </dl>
      )}

      {status === "done" && coverage.total > 0 && <p className={styles.hint}>{c.hint}</p>}
    </section>
  );
}
