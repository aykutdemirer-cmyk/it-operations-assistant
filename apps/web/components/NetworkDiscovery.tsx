"use client";

import { useState } from "react";

import { scanNetwork, type ScanResult } from "@/lib/api";

type Status = "idle" | "scanning" | "done" | "error";

export function NetworkDiscovery() {
  const [cidr, setCidr] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<ScanResult | null>(null);
  const [errorMessage, setErrorMessage] = useState("");

  async function handleScan() {
    setStatus("scanning");
    setErrorMessage("");

    try {
      const scanResult = await scanNetwork(cidr);
      setResult(scanResult);
      setStatus("done");
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Tarama başarısız",
      );
      setStatus("error");
    }
  }

  return (
    <section>
      <h2>Network Discovery</h2>

      <label htmlFor="cidr-input">CIDR:</label>
      <input
        id="cidr-input"
        value={cidr}
        onChange={(event) => setCidr(event.target.value)}
        placeholder="10.0.5.0/24"
      />
      <button onClick={handleScan} disabled={status === "scanning"}>
        Scan Network
      </button>

      {status === "scanning" && <p>Scanning...</p>}
      {status === "error" && <p role="alert">{errorMessage}</p>}

      {status === "done" && result && (
        <table>
          <thead>
            <tr>
              <th>IP</th>
              <th>Hostname</th>
              <th>MAC Address</th>
              <th>Vendor</th>
              <th>Device Type</th>
              <th>Confidence</th>
              <th>Open Ports</th>
              <th>Status</th>
              <th>Latency</th>
            </tr>
          </thead>
          <tbody>
            {result.hosts.map((host) => (
              <tr key={host.ip}>
                <td>{host.ip}</td>
                <td>{host.hostname ?? "-"}</td>
                <td>{host.mac_address ?? "-"}</td>
                <td>{host.vendor ?? "-"}</td>
                <td>{host.device_type}</td>
                <td>{host.confidence.toUpperCase()}</td>
                <td>
                  {host.open_ports.length > 0
                    ? host.open_ports.map((p) => p.port).join(", ")
                    : "-"}
                </td>
                <td>{host.status === "up" ? "🟢 UP" : "🔴 DOWN"}</td>
                <td>
                  {host.latency_ms != null ? `${host.latency_ms}ms` : "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
