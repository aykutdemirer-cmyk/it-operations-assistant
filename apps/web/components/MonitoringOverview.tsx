"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  fetchMonitoringHistory,
  type BandwidthSample,
  type MonitoringHistoryResponse,
  type PollLogEntry,
  type SnmpInterfaceInfo,
  type SnmpPollResult,
} from "@/lib/api";
import { useDashboardData } from "@/lib/DashboardDataProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { timeAgo } from "@/lib/time";
import { useAutoRefresh } from "@/lib/useAutoRefresh";
import styles from "./MonitoringOverview.module.css";

type FetchStatus = "loading" | "done" | "error";

type InterfaceRow = { result: SnmpPollResult; iface: SnmpInterfaceInfo };

const REFRESH_INTERVAL_MS = 7000;

function toMbps(bps: number | null): number | null {
  return bps == null ? null : Math.round((bps / 1_000_000) * 10) / 10;
}

function formatMbps(bps: number | null): string {
  const mbps = toMbps(bps);
  return mbps == null ? "—" : `${mbps.toFixed(1)} Mbps`;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString();
}

/**
 * `/monitoring` sayfası — Faz: arka plan SNMP polling worker'ının
 * (`app/snmp/scheduler.py`) periyodik olarak topladığı canlı telemetriye
 * bağlı gerçek bir NOC paneli. `GET /api/monitoring/history` hiçbir yeni
 * poll TETİKLEMEZ (yalnızca arka planda zaten toplanmış, süreç-içi
 * önbelleği okur) — bu yüzden 7 saniyede bir sessizce (`useAutoRefresh`,
 * layout sıçraması olmadan) yeniden çekilir. CPU/Bellek artık
 * HOST-RESOURCES-MIB destekleyen cihazlarda GERÇEK veri taşır (bkz.
 * `app/snmp/client.py::_get_cpu_memory_info`); desteklemeyen cihazlarda
 * (çoğu switch/router/firewall) dürüstçe "—" gösterilir, asla uydurulmaz.
 */
export function MonitoringOverview() {
  const { assets } = useDashboardData();
  const { t } = useLocale();

  const [history, setHistory] = useState<MonitoringHistoryResponse | null>(null);
  const [status, setStatus] = useState<FetchStatus>("loading");

  const load = useCallback(() => {
    fetchMonitoringHistory()
      .then((data) => {
        setHistory(data);
        setStatus("done");
      })
      .catch(() => setStatus((prev) => (prev === "done" ? prev : "error")));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useAutoRefresh(load, REFRESH_INTERVAL_MS);

  const latestBatch = history?.latest_batch ?? null;
  const pollLog: PollLogEntry[] = history?.poll_log ?? [];
  const bandwidthHistory: BandwidthSample[] = history?.bandwidth_history ?? [];

  const assetsById = new Map(assets.map((asset) => [asset.id, asset]));
  function deviceLabel(assetId: string): string {
    const asset = assetsById.get(assetId);
    return asset?.hostname ?? asset?.ip_address ?? assetId;
  }

  // --- KPI hesaplamaları — hepsi gerçek veriden türetilir, uydurma yok ---
  const coveragePercent =
    latestBatch && latestBatch.total > 0
      ? Math.round((latestBatch.polled / latestBatch.total) * 100)
      : 0;

  const upAssets = assets.filter((a) => a.status === "up").length;
  const healthScore = assets.length > 0 ? Math.round((upAssets / assets.length) * 100) : 0;

  const latestSample = bandwidthHistory[bandwidthHistory.length - 1] ?? null;
  const totalInMbps = toMbps(latestSample?.total_in_bps ?? null);
  const totalOutMbps = toMbps(latestSample?.total_out_bps ?? null);

  const realLatencies = assets.map((a) => a.latency_ms).filter((v): v is number => v != null);
  const avgLatency =
    realLatencies.length > 0
      ? Math.round((realLatencies.reduce((sum, v) => sum + v, 0) / realLatencies.length) * 10) / 10
      : null;

  // --- Bant genişliği grafiği verisi (Recharts) ---
  const chartData = bandwidthHistory.map((sample) => ({
    time: formatTime(sample.ts),
    [t.monitoring.bandwidthChart.ingress]: toMbps(sample.total_in_bps),
    [t.monitoring.bandwidthChart.egress]: toMbps(sample.total_out_bps),
  }));

  // --- Arayüz tablosu ---
  const interfaceRows: InterfaceRow[] = (latestBatch?.results ?? []).flatMap((result) =>
    result.interfaces.map((iface) => ({ result, iface })),
  );

  return (
    <section className={styles.wrap}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{t.monitoring.title}</h1>
          <p className={styles.subtitle}>{t.monitoring.subtitle}</p>
        </div>
        <button type="button" className={styles.refreshButton} onClick={load}>
          {t.common.refresh}
        </button>
      </div>

      {status === "loading" && <p className={styles.status}>{t.common.loading}</p>}
      {status === "error" && <p className={styles.status}>{t.monitoring.loadError}</p>}

      {status !== "error" && !latestBatch && (
        <p className={styles.notice}>{t.monitoring.waitingForFirstPoll}</p>
      )}

      {status !== "loading" && (
        <>
          <div className={styles.kpiBar}>
            <div className={styles.kpiCard}>
              <div className={styles.gauge}>
                <div
                  className={styles.gaugeFill}
                  style={{ background: `conic-gradient(var(--accent) ${coveragePercent}%, var(--surface-raised) 0)` }}
                >
                  <span className={styles.gaugeValue}>{coveragePercent}%</span>
                </div>
              </div>
              <span className={styles.kpiLabel}>{t.monitoring.kpi.coverage}</span>
            </div>
            <div className={styles.kpiCard}>
              <span className={styles.kpiValue}>{latestBatch?.polled ?? 0}</span>
              <span className={styles.kpiLabel}>{t.monitoring.kpi.monitoredDevices}</span>
            </div>
            <div className={styles.kpiCard}>
              <span className={`${styles.kpiValue} ${healthScore >= 80 ? styles.kpiGood : healthScore >= 50 ? styles.kpiWarn : styles.kpiBad}`}>
                {healthScore}%
              </span>
              <span className={styles.kpiLabel}>{t.monitoring.kpi.healthScore}</span>
            </div>
            <div className={styles.kpiCard}>
              <span className={styles.kpiValue}>
                {totalInMbps == null && totalOutMbps == null
                  ? "—"
                  : `↓${(totalInMbps ?? 0).toFixed(1)} / ↑${(totalOutMbps ?? 0).toFixed(1)} Mbps`}
              </span>
              <span className={styles.kpiLabel}>{t.monitoring.kpi.totalBandwidth}</span>
            </div>
            <div className={styles.kpiCard}>
              <span className={styles.kpiValue}>
                {avgLatency == null ? t.monitoring.kpi.noLatencyData : `${avgLatency} ms`}
              </span>
              <span className={styles.kpiLabel}>{t.monitoring.kpi.avgLatency}</span>
            </div>
          </div>

          <div className={styles.panel}>
            <h2 className={styles.panelTitle}>{t.monitoring.bandwidthChart.title}</h2>
            {chartData.length === 0 ? (
              <p className={styles.noData}>{t.monitoring.bandwidthChart.noData}</p>
            ) : (
              <div className={styles.chartWrap}>
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="inGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--status-up)" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="var(--status-up)" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="outGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--accent)" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="var(--accent)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                    <XAxis dataKey="time" tick={{ fontSize: 11 }} stroke="var(--text-muted)" />
                    <YAxis tick={{ fontSize: 11 }} stroke="var(--text-muted)" unit=" Mbps" />
                    <Tooltip
                      contentStyle={{
                        background: "var(--surface-raised)",
                        border: "1px solid var(--border-strong)",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey={t.monitoring.bandwidthChart.ingress}
                      stroke="var(--status-up)"
                      fill="url(#inGradient)"
                      strokeWidth={2}
                      connectNulls
                    />
                    <Area
                      type="monotone"
                      dataKey={t.monitoring.bandwidthChart.egress}
                      stroke="var(--accent)"
                      fill="url(#outGradient)"
                      strokeWidth={2}
                      connectNulls
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          <div className={styles.twoColumn}>
            <div className={styles.panel}>
              <h2 className={styles.panelTitle}>{t.monitoring.interfaceTable.title}</h2>
              {interfaceRows.length === 0 ? (
                <p className={styles.noData}>{t.monitoring.noData}</p>
              ) : (
                <div className={styles.tableWrap}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>{t.monitoring.interfaceTable.columns.device}</th>
                        <th>{t.monitoring.interfaceTable.columns.interfaceName}</th>
                        <th>{t.monitoring.interfaceTable.columns.status}</th>
                        <th>{t.monitoring.interfaceTable.columns.inMbps}</th>
                        <th>{t.monitoring.interfaceTable.columns.outMbps}</th>
                        <th>{t.monitoring.interfaceTable.columns.errors}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {interfaceRows.map(({ result, iface }) => {
                        const errorCount = (iface.if_in_errors ?? 0) + (iface.if_out_errors ?? 0);
                        const up = iface.if_oper_status === "up";
                        return (
                          <tr key={`${result.asset_id}:${iface.if_index}`}>
                            <td>{deviceLabel(result.asset_id)}</td>
                            <td>{iface.if_name ?? iface.if_descr ?? `#${iface.if_index}`}</td>
                            <td>
                              <span className={styles.statusCell}>
                                <span className={`${styles.dot} ${up ? styles.dotUp : styles.dotDown}`} />
                                {iface.if_oper_status ?? "—"}
                              </span>
                            </td>
                            <td>{formatMbps(iface.if_in_bps)}</td>
                            <td>{formatMbps(iface.if_out_bps)}</td>
                            <td className={errorCount > 0 ? styles.errorCell : undefined}>{errorCount}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className={styles.panel}>
              <h2 className={styles.panelTitle}>{t.monitoring.pollLog.title}</h2>
              {pollLog.length === 0 ? (
                <p className={styles.noData}>{t.monitoring.pollLog.empty}</p>
              ) : (
                <div className={styles.tableWrap}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>{t.monitoring.pollLog.columns.device}</th>
                        <th>{t.monitoring.pollLog.columns.status}</th>
                        <th>{t.monitoring.pollLog.columns.duration}</th>
                        <th>{t.monitoring.pollLog.columns.oidCount}</th>
                        <th>{t.monitoring.pollLog.columns.time}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pollLog.map((entry, idx) => (
                        <tr key={`${entry.asset_id}:${entry.polled_at}:${idx}`}>
                          <td>{deviceLabel(entry.asset_id)}</td>
                          <td>
                            <span className={styles.statusCell}>
                              <span
                                className={`${styles.dot} ${
                                  entry.status === "success" || entry.status === "partial"
                                    ? styles.dotUp
                                    : entry.status === "not_configured"
                                      ? styles.dotMuted
                                      : styles.dotDown
                                }`}
                              />
                              {t.monitoring.pollStatus[entry.status]}
                            </span>
                          </td>
                          <td>{entry.duration_ms != null ? `${Math.round(entry.duration_ms)}ms` : "—"}</td>
                          <td>{entry.oid_count}</td>
                          <td>{timeAgo(entry.polled_at, t.timeAgo)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
