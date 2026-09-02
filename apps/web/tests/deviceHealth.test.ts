import { describe, expect, it } from "vitest";

import type { Alert } from "@/lib/alerts";
import type { Asset } from "@/lib/api";
import { computeDeviceHealth } from "@/lib/deviceHealth";

let nextId = 0;

function asset(status: "up" | "down"): Asset {
  nextId += 1;
  return {
    id: `asset-${nextId}`,
    ip_address: "10.0.0.1",
    hostname: null,
    mac_address: null,
    vendor: null,
    device_type: "unknown",
    confidence: "low",
    evidence: [],
    open_ports: [],
    status,
    latency_ms: null,
    last_seen: "2026-08-26T00:00:00Z",
    created_at: "2026-08-26T00:00:00Z",
    updated_at: "2026-08-26T00:00:00Z",
  };
}

function warningAlert(assetId: string): Alert {
  return {
    id: `alert-${assetId}`,
    rule: "high_risk_port",
    severity: "WARNING",
    assetId,
    assetLabel: assetId,
    message: "test warning",
    detectedAt: "2026-08-26T00:00:00Z",
  };
}

describe("computeDeviceHealth", () => {
  it("returns all zeros for an empty fleet", () => {
    const health = computeDeviceHealth([], []);

    expect(health).toEqual({
      critical: 0,
      warning: 0,
      healthy: 0,
      unmonitored: 0,
      total: 0,
    });
  });

  it("classifies a down asset as critical regardless of alerts", () => {
    const downAsset = asset("down");

    const health = computeDeviceHealth([downAsset], [warningAlert(downAsset.id)]);

    expect(health.critical).toBe(1);
    expect(health.warning).toBe(0);
    expect(health.healthy).toBe(0);
  });

  it("classifies an up asset with a WARNING alert as warning", () => {
    const upAsset = asset("up");

    const health = computeDeviceHealth([upAsset], [warningAlert(upAsset.id)]);

    expect(health.warning).toBe(1);
    expect(health.healthy).toBe(0);
  });

  it("classifies an up asset with no alerts as healthy", () => {
    const upAsset = asset("up");

    const health = computeDeviceHealth([upAsset], []);

    expect(health.healthy).toBe(1);
    expect(health.warning).toBe(0);
  });

  it("sets unmonitored equal to the total asset count — no SNMP configured anywhere yet", () => {
    const assets = [asset("up"), asset("up"), asset("down")];

    const health = computeDeviceHealth(assets, []);

    expect(health.unmonitored).toBe(3);
    expect(health.total).toBe(3);
  });
});
