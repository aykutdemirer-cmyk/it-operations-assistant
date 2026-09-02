"use client";

import { useDashboardData } from "@/lib/DashboardDataProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./NetworkPerformance.module.css";

/**
 * Bant genişliği/interface performansı SNMP `ifInOctets`/`ifOutOctets`
 * verisine dayanır (bkz. `apps/api/app/snmp/`). Henüz gerçek bir ajan
 * yok — bu yüzden bu bölüm her zaman dürüstçe "no data" durumunu
 * gösterir; hiçbir sayı/grafik uydurulmaz.
 */
export function NetworkPerformance() {
  const { assetsStatus: status } = useDashboardData();
  const { t } = useLocale();
  const n = t.dashboard.networkPerformance;

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>{n.title}</h2>
        <p className={styles.subtitle}>{n.subtitle}</p>
      </div>

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}

      {status !== "loading" && (
        <div className={styles.sections}>
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>{n.networkLoad}</h3>
            <p className={styles.noData}>{n.noInterfaceData}</p>
          </div>
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>{n.topTalkers}</h3>
            <p className={styles.noData}>{n.noInterfaceData}</p>
          </div>
        </div>
      )}
    </section>
  );
}
