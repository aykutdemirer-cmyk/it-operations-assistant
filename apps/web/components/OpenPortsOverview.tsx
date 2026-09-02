"use client";

import { useDashboardData } from "@/lib/DashboardDataProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { aggregateOpenPorts, type PortRisk } from "@/lib/portRisk";
import styles from "./OpenPortsOverview.module.css";

const RISK_CLASS: Record<string, string> = {
  LOW: "riskLow",
  MEDIUM: "riskMedium",
  HIGH: "riskHigh",
};

export function OpenPortsOverview() {
  const { assets, assetsStatus: status } = useDashboardData();
  const { t } = useLocale();

  const ports = aggregateOpenPorts(assets);
  const o = t.dashboard.openPorts;
  const riskLabel: Record<PortRisk, string> = {
    LOW: t.risk.low,
    MEDIUM: t.risk.medium,
    HIGH: t.risk.high,
  };

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>{o.title}</h2>
        <p className={styles.subtitle}>{o.subtitle}</p>
      </div>

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {status === "error" && (
        <p className={styles.status}>{t.common.unableToLoad}</p>
      )}
      {status === "done" && ports.length === 0 && (
        <p className={styles.status}>{o.noOpenPorts}</p>
      )}

      {status === "done" && ports.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{o.port}</th>
                <th>{o.deviceCount}</th>
                <th>{o.risk}</th>
              </tr>
            </thead>
            <tbody>
              {ports.map((entry) => (
                <tr key={entry.port}>
                  <td className={styles.mono}>{entry.port}</td>
                  <td>{entry.deviceCount}</td>
                  <td>
                    <span
                      className={`${styles.badge} ${styles[RISK_CLASS[entry.risk]]}`}
                    >
                      {riskLabel[entry.risk]}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
