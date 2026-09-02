"use client";

import { useEffect, useState } from "react";

import { fetchMonitoring, type PollBatchResult, type SnmpInterfaceInfo, type SnmpPollResult } from "@/lib/api";
import { useDashboardData } from "@/lib/DashboardDataProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./MonitoringOverview.module.css";

type MonitoringFetchStatus = "loading" | "done" | "error";

type InterfaceRow = { result: SnmpPollResult; iface: SnmpInterfaceInfo };

/**
 * `/monitoring` sayfası — Faz 24'te eklenen gerçek `GET /api/monitoring`
 * endpoint'ine bağlı (Faz 27). SNMP Coverage/Monitored Devices artık
 * gerçek `PollBatchResult` sayılarından (`total`/`polled`) hesaplanıyor
 * — Faz 6'nın `computeMonitoringCoverage` heuristiği (assets tablosundan
 * tahmini) yerine. Interface Monitoring/Bandwidth bölümleri gerçek
 * poll edilen interface'leri gösterir (bugün pratikte yalnızca
 * `SNMP_TARGET_ASSET_ID` ile eşleşen tek bir hedef varsa dolu olur).
 * CPU/Memory backend'de hiç poll edilmediği için (HOST-RESOURCES-MIB
 * implemente edilmedi) HER ZAMAN "veri yok" gösterir — bu bir eksik
 * değil, dürüst bir sınır.
 */
export function MonitoringOverview() {
  const { assets } = useDashboardData();
  const { t } = useLocale();

  const [monitoring, setMonitoring] = useState<PollBatchResult | null>(null);
  const [status, setStatus] = useState<MonitoringFetchStatus>("loading");

  useEffect(() => {
    let cancelled = false;

    fetchMonitoring()
      .then((data) => {
        if (cancelled) return;
        setMonitoring(data);
        setStatus("done");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const assetsById = new Map(assets.map((asset) => [asset.id, asset]));

  function deviceLabel(assetId: string): string {
    const asset = assetsById.get(assetId);
    return asset?.hostname ?? asset?.ip_address ?? assetId;
  }

  const coveragePercent =
    monitoring && monitoring.total > 0 ? Math.round((monitoring.polled / monitoring.total) * 100) : 0;

  const interfaceRows: InterfaceRow[] = (monitoring?.results ?? []).flatMap((result) =>
    result.interfaces.map((iface) => ({ result, iface })),
  );
  const bandwidthRows = interfaceRows.filter(
    ({ iface }) => iface.if_in_bps != null || iface.if_out_bps != null,
  );
  const attemptedPolls = (monitoring?.results ?? []).filter((r) => r.status !== "not_configured");

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>{t.monitoring.title}</h2>
        <p className={styles.subtitle}>{t.monitoring.subtitle}</p>
      </div>

      {status !== "error" && attemptedPolls.length === 0 && (
        <p className={styles.notice}>{t.monitoring.notConfiguredMessage}</p>
      )}

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {status === "error" && <p className={styles.status}>{t.monitoring.loadError}</p>}

      {status === "done" && monitoring && (
        <div className={styles.statGrid}>
          <div className={styles.stat}>
            <span className={styles.value}>{coveragePercent}%</span>
            <span className={styles.label}>{t.monitoring.snmpCoverage}</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.value}>{monitoring.polled}</span>
            <span className={styles.label}>{t.monitoring.monitoredDevices}</span>
          </div>
        </div>
      )}

      <div className={styles.sections}>
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>{t.monitoring.interfaceMonitoring}</h3>
          {interfaceRows.length === 0 ? (
            <p className={styles.noData}>{t.monitoring.noData}</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>{t.monitoring.columns.device}</th>
                    <th>{t.monitoring.columns.interface}</th>
                    <th>{t.monitoring.columns.status}</th>
                  </tr>
                </thead>
                <tbody>
                  {interfaceRows.map(({ result, iface }) => (
                    <tr key={`${result.asset_id}:${iface.if_index}`}>
                      <td>{deviceLabel(result.asset_id)}</td>
                      <td>{iface.if_name ?? iface.if_descr ?? `#${iface.if_index}`}</td>
                      <td>{iface.if_oper_status ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>{t.monitoring.bandwidth}</h3>
          {bandwidthRows.length === 0 ? (
            <p className={styles.noData}>{t.monitoring.noData}</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>{t.monitoring.columns.interface}</th>
                    <th>{t.monitoring.columns.inBps}</th>
                    <th>{t.monitoring.columns.outBps}</th>
                  </tr>
                </thead>
                <tbody>
                  {bandwidthRows.map(({ result, iface }) => (
                    <tr key={`${result.asset_id}:${iface.if_index}`}>
                      <td>{iface.if_name ?? iface.if_descr ?? `#${iface.if_index}`}</td>
                      <td>{formatMbps(iface.if_in_bps)}</td>
                      <td>{formatMbps(iface.if_out_bps)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>{t.monitoring.cpu}</h3>
          <p className={styles.noData}>{t.monitoring.noData}</p>
        </div>
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>{t.monitoring.memory}</h3>
          <p className={styles.noData}>{t.monitoring.noData}</p>
        </div>
      </div>

      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>{t.monitoring.recentPolls}</h3>
        {attemptedPolls.length === 0 ? (
          <p className={styles.noData}>{t.monitoring.noData}</p>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>{t.monitoring.columns.device}</th>
                  <th>{t.monitoring.columns.pollStatus}</th>
                  <th>{t.monitoring.columns.duration}</th>
                </tr>
              </thead>
              <tbody>
                {attemptedPolls.map((result) => (
                  <tr key={result.asset_id}>
                    <td>{deviceLabel(result.asset_id)}</td>
                    <td>{t.monitoring.pollStatus[result.status]}</td>
                    <td>{result.duration_ms != null ? `${Math.round(result.duration_ms)}ms` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

function formatMbps(bps: number | null): string {
  if (bps == null) return "—";
  return `${(bps / 1_000_000).toFixed(1)} Mbps`;
}
