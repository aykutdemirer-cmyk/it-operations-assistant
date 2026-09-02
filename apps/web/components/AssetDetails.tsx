"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { computeAlerts, type AlertSeverity } from "@/lib/alerts";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import type { translations } from "@/lib/i18n/translations";
import { classifyPortRisk, type PortRisk } from "@/lib/portRisk";
import { timeAgo } from "@/lib/time";
import type { Asset } from "@/lib/api";
import { AssetAgentPanel } from "@/components/AssetAgentPanel";
import { AssetSnmpPanel } from "@/components/AssetSnmpPanel";
import styles from "./AssetDetails.module.css";

type Dict = (typeof translations)["tr"];
type TabKey =
  | "overview"
  | "network"
  | "discovery"
  | "ports"
  | "monitoring"
  | "snmp"
  | "agent"
  | "alerts";

const SEVERITY_CLASS: Record<AlertSeverity, string> = {
  CRITICAL: "severityCritical",
  WARNING: "severityWarning",
  INFO: "severityInfo",
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

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

function riskClass(risk: PortRisk): string {
  if (risk === "HIGH") return styles.riskHigh;
  if (risk === "MEDIUM") return styles.riskMedium;
  return styles.riskLow;
}

type Props = {
  asset: Asset;
  onClose: () => void;
};

export function AssetDetails({ asset, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const { t } = useLocale();
  const assetAlerts = computeAlerts([asset], t.alertMessages);
  const d = t.assetDetails;

  const TABS: { key: TabKey; label: string }[] = [
    { key: "overview", label: d.tabs.overview },
    { key: "network", label: d.tabs.network },
    { key: "discovery", label: d.tabs.discovery },
    { key: "ports", label: d.tabs.ports },
    { key: "monitoring", label: d.tabs.monitoring },
    { key: "snmp", label: d.tabs.snmp },
    { key: "agent", label: d.tabs.agent },
    { key: "alerts", label: d.tabs.alerts },
  ];

  const severityLabel: Record<AlertSeverity, string> = {
    CRITICAL: t.severity.critical,
    WARNING: t.severity.warning,
    INFO: t.severity.info,
  };

  const riskLabel: Record<PortRisk, string> = {
    LOW: t.risk.low,
    MEDIUM: t.risk.medium,
    HIGH: t.risk.high,
  };

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
        aria-label={d.ariaLabel}
      >
        <div className={styles.panelHeader}>
          <h3 className={styles.panelTitle}>
            {asset.hostname ?? asset.ip_address}
          </h3>
          <button
            className={styles.closeButton}
            onClick={onClose}
            aria-label={d.closeButton}
          >
            ✕
          </button>
        </div>

        <Link
          className={styles.topologyLink}
          href={`/topology?ip=${encodeURIComponent(asset.ip_address)}`}
        >
          🕸️ {t.common.viewInTopology}
        </Link>

        <div className={styles.tabs} role="tablist">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              role="tab"
              id={`asset-tab-${tab.key}`}
              aria-selected={activeTab === tab.key}
              aria-controls={`asset-panel-${tab.key}`}
              className={`${styles.tab} ${activeTab === tab.key ? styles.tabActive : ""}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === "overview" && (
          <dl
            className={styles.fields}
            role="tabpanel"
            id="asset-panel-overview"
            aria-labelledby="asset-tab-overview"
          >
            <div className={styles.field}>
              <dt>{d.fields.hostname}</dt>
              <dd>{asset.hostname ?? "-"}</dd>
            </div>
            <div className={styles.field}>
              <dt>{d.fields.ipAddress}</dt>
              <dd>{asset.ip_address}</dd>
            </div>
            <div className={styles.field}>
              <dt>{d.fields.deviceType}</dt>
              <dd>{deviceTypeLabel(asset.device_type, t)}</dd>
            </div>
            <div className={styles.field}>
              <dt>{d.fields.status}</dt>
              <dd>
                {asset.status === "up" ? `🟢 ${t.status.up}` : `🔴 ${t.status.down}`}
              </dd>
            </div>
            <div className={styles.field}>
              <dt>{d.fields.confidence}</dt>
              <dd>{t.confidence[asset.confidence]}</dd>
            </div>
            <div className={styles.field}>
              <dt>{d.fields.lastSeen}</dt>
              <dd>{formatTimestamp(asset.last_seen)}</dd>
            </div>
          </dl>
        )}

        {activeTab === "network" && (
          <dl
            className={styles.fields}
            role="tabpanel"
            id="asset-panel-network"
            aria-labelledby="asset-tab-network"
          >
            <div className={styles.field}>
              <dt>{d.fields.ipAddress}</dt>
              <dd>{asset.ip_address}</dd>
            </div>
            <div className={styles.field}>
              <dt>{d.fields.macAddress}</dt>
              <dd>{asset.mac_address ?? "-"}</dd>
            </div>
            <div className={styles.field}>
              <dt>{d.fields.vendor}</dt>
              <dd>{asset.vendor ?? "-"}</dd>
            </div>
            <div className={styles.field}>
              <dt>{d.fields.latency}</dt>
              <dd>{asset.latency_ms != null ? `${asset.latency_ms}ms` : "-"}</dd>
            </div>
          </dl>
        )}

        {activeTab === "discovery" && (
          <dl
            className={styles.fields}
            role="tabpanel"
            id="asset-panel-discovery"
            aria-labelledby="asset-tab-discovery"
          >
            <div className={styles.field}>
              <dt>{d.fields.confidence}</dt>
              <dd>{t.confidence[asset.confidence]}</dd>
            </div>
            <div className={styles.field}>
              <dt>{d.fields.firstDiscovered}</dt>
              <dd>{formatTimestamp(asset.created_at)}</dd>
            </div>
            <div className={styles.field}>
              <dt>{d.fields.lastUpdated}</dt>
              <dd>{formatTimestamp(asset.updated_at)}</dd>
            </div>
            <div className={styles.field}>
              <dt>{d.fields.evidence}</dt>
              <dd>
                {asset.evidence.length > 0 ? (
                  <ul className={styles.evidenceList}>
                    {asset.evidence.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  "-"
                )}
              </dd>
            </div>
          </dl>
        )}

        {activeTab === "ports" && (
          <div
            className={styles.fields}
            role="tabpanel"
            id="asset-panel-ports"
            aria-labelledby="asset-tab-ports"
          >
            {asset.open_ports.length > 0 ? (
              <table className={styles.portsTable}>
                <thead>
                  <tr>
                    <th>{d.ports.port}</th>
                    <th>{d.ports.status}</th>
                    <th>{d.ports.risk}</th>
                  </tr>
                </thead>
                <tbody>
                  {asset.open_ports.map((port) => {
                    const risk = classifyPortRisk(port.port);
                    return (
                      <tr key={port.port}>
                        <td className={styles.mono}>{port.port}</td>
                        <td>{port.status}</td>
                        <td>
                          <span className={`${styles.badge} ${riskClass(risk)}`}>
                            {riskLabel[risk]}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p className={styles.noData}>{d.ports.noOpenPorts}</p>
            )}
          </div>
        )}

        {activeTab === "monitoring" && (
          <dl
            className={styles.fields}
            role="tabpanel"
            id="asset-panel-monitoring"
            aria-labelledby="asset-tab-monitoring"
          >
            <div className={styles.field}>
              <dt>{d.monitoring.snmpStatus}</dt>
              <dd className={styles.noData}>{d.monitoring.notMonitored}</dd>
            </div>
            <div className={styles.field}>
              <dt>{d.monitoring.cpuUsage}</dt>
              <dd className={styles.noData}>{d.monitoring.noDataAvailable}</dd>
            </div>
            <div className={styles.field}>
              <dt>{d.monitoring.memoryUsage}</dt>
              <dd className={styles.noData}>{d.monitoring.noDataAvailable}</dd>
            </div>
            <div className={styles.field}>
              <dt>{d.monitoring.uptime}</dt>
              <dd className={styles.noData}>{d.monitoring.noDataAvailable}</dd>
            </div>
            <div className={styles.field}>
              <dt>{d.monitoring.temperature}</dt>
              <dd className={styles.noData}>{d.monitoring.noDataAvailable}</dd>
            </div>
            <div className={styles.field}>
              <dt>{d.monitoring.networkInterfaces}</dt>
              <dd className={styles.noData}>{d.monitoring.noInterfaceData}</dd>
            </div>
            <p className={styles.monitoringHint}>{d.monitoring.hint}</p>
          </dl>
        )}

        {activeTab === "snmp" && (
          <div
            className={styles.fields}
            role="tabpanel"
            id="asset-panel-snmp"
            aria-labelledby="asset-tab-snmp"
          >
            <AssetSnmpPanel assetId={asset.id} />
          </div>
        )}

        {activeTab === "agent" && (
          <div
            className={styles.fields}
            role="tabpanel"
            id="asset-panel-agent"
            aria-labelledby="asset-tab-agent"
          >
            <AssetAgentPanel assetId={asset.id} />
          </div>
        )}

        {activeTab === "alerts" && (
          <div
            className={styles.fields}
            role="tabpanel"
            id="asset-panel-alerts"
            aria-labelledby="asset-tab-alerts"
          >
            {assetAlerts.length > 0 ? (
              <ul className={styles.alertList}>
                {assetAlerts.map((alert) => (
                  <li key={alert.id} className={styles.alertItem}>
                    <span
                      className={`${styles.badge} ${styles[SEVERITY_CLASS[alert.severity]]}`}
                    >
                      {severityLabel[alert.severity]}
                    </span>
                    <span className={styles.alertMessage}>{alert.message}</span>
                    <span className={styles.alertTime}>
                      {timeAgo(alert.detectedAt, t.timeAgo)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className={styles.noData}>{d.alerts.noAlertsForDevice}</p>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
