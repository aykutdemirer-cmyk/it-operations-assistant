"use client";

import { useState } from "react";

import { scanNetwork, type ScanResult } from "@/lib/api";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import type { translations } from "@/lib/i18n/translations";
import styles from "./NetworkDiscovery.module.css";

type Dict = (typeof translations)["tr"];
type Status = "idle" | "scanning" | "done" | "error";

function deviceTypeLabel(deviceType: string, t: Dict): string {
  return (
    t.deviceType[deviceType as keyof Dict["deviceType"]] ??
    deviceType
      .split("_")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ")
  );
}

export function NetworkDiscovery() {
  const [cidr, setCidr] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<ScanResult | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const { t } = useLocale();

  function summarize(scanResult: ScanResult): string {
    const openPorts = scanResult.hosts.reduce(
      (sum, host) => sum + host.open_ports.length,
      0,
    );
    return `${scanResult.alive_hosts} ${t.discovery.hostsDiscovered} · ${openPorts} ${t.discovery.openPortsFound}`;
  }

  async function handleScan() {
    setStatus("scanning");
    setErrorMessage("");

    try {
      const scanResult = await scanNetwork(cidr);
      setResult(scanResult);
      setStatus("done");
      window.dispatchEvent(new CustomEvent("network-scan-completed"));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : t.discovery.error);
      setStatus("error");
    }
  }

  return (
    <section className={styles.card}>
      <h2 className={styles.title}>{t.discovery.title}</h2>

      <div className={styles.controls}>
        <label className={styles.label} htmlFor="cidr-input">
          {t.discovery.cidrLabel}
        </label>
        <input
          id="cidr-input"
          className={styles.input}
          value={cidr}
          onChange={(event) => setCidr(event.target.value)}
          placeholder="10.0.5.0/24"
        />
        <button
          className={styles.scanButton}
          onClick={handleScan}
          disabled={status === "scanning"}
        >
          {t.discovery.scanButton}
        </button>
      </div>

      {status === "scanning" && (
        <p className={styles.scanning}>
          <span className={styles.spinner} aria-hidden="true" />
          {t.discovery.scanning}
        </p>
      )}
      {status === "error" && (
        <p className={styles.error} role="alert">
          {errorMessage}
        </p>
      )}

      {status === "done" && result && (
        <>
          <p className={styles.summary}>{summarize(result)}</p>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>{t.assets.columns.ipAddress}</th>
                  <th>{t.assets.columns.hostname}</th>
                  <th>{t.assets.columns.macAddress}</th>
                  <th>{t.assets.columns.vendor}</th>
                  <th>{t.assets.columns.deviceType}</th>
                  <th>{t.assets.columns.confidence}</th>
                  <th>{t.assets.columns.openPorts}</th>
                  <th>{t.assets.columns.status}</th>
                  <th>{t.assets.columns.latency}</th>
                </tr>
              </thead>
              <tbody>
                {result.hosts.map((host) => (
                  <tr key={host.ip}>
                    <td>{host.ip}</td>
                    <td>{host.hostname ?? "-"}</td>
                    <td>{host.mac_address ?? "-"}</td>
                    <td>{host.vendor ?? "-"}</td>
                    <td>{deviceTypeLabel(host.device_type, t)}</td>
                    <td>{t.confidence[host.confidence]}</td>
                    <td>
                      {host.open_ports.length > 0
                        ? host.open_ports.map((p) => p.port).join(", ")
                        : "-"}
                    </td>
                    <td>
                      {host.status === "up" ? `🟢 ${t.status.up}` : `🔴 ${t.status.down}`}
                    </td>
                    <td>
                      {host.latency_ms != null ? `${host.latency_ms}ms` : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
