import { describe, expect, it } from "vitest";

import type { Asset } from "@/lib/api";
import { computeMonitoringCoverage } from "@/lib/monitoringCoverage";

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

describe("computeMonitoringCoverage", () => {
  it("reports zero SNMP-enabled devices when no assigned count is given (backward compatible default)", () => {
    const coverage = computeMonitoringCoverage([asset("up"), asset("up")]);

    expect(coverage.snmpEnabled).toBe(0);
  });

  it("reports snmpDisabled equal to the total asset count when nothing is assigned", () => {
    const assets = [asset("up"), asset("up"), asset("down")];

    const coverage = computeMonitoringCoverage(assets);

    expect(coverage.total).toBe(3);
    expect(coverage.snmpDisabled).toBe(3);
  });

  it("reflects the real assigned SNMP profile count (Faz 29.5)", () => {
    const assets = [asset("up"), asset("up"), asset("down")];

    const coverage = computeMonitoringCoverage(assets, 2);

    expect(coverage.total).toBe(3);
    expect(coverage.snmpEnabled).toBe(2);
    expect(coverage.snmpDisabled).toBe(1);
  });

  it("caps snmpEnabled at the real asset total, never exceeding it", () => {
    const assets = [asset("up")];

    const coverage = computeMonitoringCoverage(assets, 99);

    expect(coverage.snmpEnabled).toBe(1);
    expect(coverage.snmpDisabled).toBe(0);
  });

  it("counts down assets as unreachable", () => {
    const assets = [asset("up"), asset("down"), asset("down")];

    const coverage = computeMonitoringCoverage(assets);

    expect(coverage.unreachable).toBe(2);
  });

  it("returns zeros for an empty fleet", () => {
    const coverage = computeMonitoringCoverage([]);

    expect(coverage).toEqual({
      total: 0,
      snmpEnabled: 0,
      snmpDisabled: 0,
      unreachable: 0,
    });
  });
});
