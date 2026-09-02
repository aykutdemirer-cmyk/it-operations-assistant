import { describe, expect, it } from "vitest";

import { aggregateOpenPorts, classifyPortRisk } from "@/lib/portRisk";
import type { Asset } from "@/lib/api";

function assetWithPorts(ports: number[]): Asset {
  return {
    id: `asset-${Math.random()}`,
    ip_address: "10.0.0.1",
    hostname: null,
    mac_address: null,
    vendor: null,
    device_type: "unknown",
    confidence: "low",
    evidence: [],
    open_ports: ports.map((port) => ({
      port,
      status: "open" as const,
      latency_ms: 1,
    })),
    status: "up",
    latency_ms: null,
    last_seen: "2026-08-26T00:00:00Z",
    created_at: "2026-08-26T00:00:00Z",
    updated_at: "2026-08-26T00:00:00Z",
  };
}

describe("classifyPortRisk", () => {
  it("classifies known high-risk ports", () => {
    expect(classifyPortRisk(445)).toBe("HIGH");
    expect(classifyPortRisk(3389)).toBe("HIGH");
    expect(classifyPortRisk(5985)).toBe("HIGH");
  });

  it("classifies known medium-risk ports", () => {
    expect(classifyPortRisk(22)).toBe("MEDIUM");
    expect(classifyPortRisk(5432)).toBe("MEDIUM");
  });

  it("classifies unlisted ports as low risk", () => {
    expect(classifyPortRisk(443)).toBe("LOW");
    expect(classifyPortRisk(80)).toBe("LOW");
  });
});

describe("aggregateOpenPorts", () => {
  it("counts distinct devices per port from real asset data", () => {
    const assets = [
      assetWithPorts([443, 445]),
      assetWithPorts([443]),
      assetWithPorts([22]),
    ];

    const result = aggregateOpenPorts(assets);

    const port443 = result.find((r) => r.port === 443);
    const port445 = result.find((r) => r.port === 445);
    const port22 = result.find((r) => r.port === 22);

    expect(port443?.deviceCount).toBe(2);
    expect(port445?.deviceCount).toBe(1);
    expect(port445?.risk).toBe("HIGH");
    expect(port22?.risk).toBe("MEDIUM");
  });

  it("only includes ports that are actually present", () => {
    const result = aggregateOpenPorts([assetWithPorts([8080])]);

    expect(result).toHaveLength(1);
    expect(result[0].port).toBe(8080);
  });

  it("returns an empty list for assets with no open ports", () => {
    expect(aggregateOpenPorts([assetWithPorts([])])).toEqual([]);
  });
});
