import { describe, expect, it } from "vitest";

import { computeInfrastructureHealth } from "@/lib/health";
import type { Asset } from "@/lib/api";

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

describe("computeInfrastructureHealth", () => {
  it("returns null percentages when there are no assets", () => {
    const health = computeInfrastructureHealth([]);

    expect(health.total).toBe(0);
    expect(health.availabilityPercent).toBeNull();
    expect(health.onlinePercent).toBeNull();
    expect(health.offlinePercent).toBeNull();
  });

  it("computes online/offline counts and percentages from real assets", () => {
    const assets = [asset("up"), asset("up"), asset("up"), asset("down")];

    const health = computeInfrastructureHealth(assets);

    expect(health.total).toBe(4);
    expect(health.online).toBe(3);
    expect(health.offline).toBe(1);
    expect(health.unknown).toBe(0);
    expect(health.onlinePercent).toBe(75);
    expect(health.offlinePercent).toBe(25);
    expect(health.availabilityPercent).toBe(75);
  });

  it("treats a fully online fleet as 100% available", () => {
    const health = computeInfrastructureHealth([asset("up"), asset("up")]);

    expect(health.availabilityPercent).toBe(100);
    expect(health.offlinePercent).toBe(0);
  });
});
