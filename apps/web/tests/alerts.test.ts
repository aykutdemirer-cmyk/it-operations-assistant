import { describe, expect, it } from "vitest";

import { computeAlerts } from "@/lib/alerts";
import { tr } from "@/lib/i18n/translations";
import type { Asset, SnmpInterfaceInfo, SnmpPollResult } from "@/lib/api";

function baseInterface(overrides: Partial<SnmpInterfaceInfo> = {}): SnmpInterfaceInfo {
  return {
    if_index: 1,
    if_name: "Gi0/1",
    if_descr: "GigabitEthernet0/1",
    if_admin_status: "up",
    if_oper_status: "up",
    if_speed_bps: 1_000_000_000,
    if_in_octets: 1000,
    if_out_octets: 2000,
    if_counters_64bit: true,
    if_in_bps: 0,
    if_out_bps: 0,
    if_in_errors: 0,
    if_out_errors: 0,
    ...overrides,
  };
}

function pollResult(assetId: string, overrides: Partial<SnmpPollResult> = {}): SnmpPollResult {
  return {
    asset_id: assetId,
    polled_at: "2026-08-26T00:00:00Z",
    status: "success",
    system: {
      sys_name: "core-sw-01",
      sys_descr: null,
      sys_object_id: null,
      sys_uptime_ticks: 100,
      cpu_percent: null,
      memory_used_bytes: null,
      memory_total_bytes: null,
    },
    interfaces: [],
    error: null,
    duration_ms: 12.3,
    ...overrides,
  };
}

function baseAsset(overrides: Partial<Asset> = {}): Asset {
  return {
    id: `asset-${Math.random()}`,
    ip_address: "10.0.0.1",
    hostname: null,
    mac_address: null,
    vendor: null,
    device_type: "unknown",
    confidence: "low",
    evidence: [],
    open_ports: [],
    status: "up",
    latency_ms: null,
    last_seen: "2026-08-26T00:00:00Z",
    created_at: "2026-08-26T00:00:00Z",
    updated_at: "2026-08-26T00:00:00Z",
    ...overrides,
  };
}

describe("computeAlerts", () => {
  it("returns no alerts for a healthy asset with no issues", () => {
    const alerts = computeAlerts([baseAsset({ status: "up", latency_ms: 10 })], tr.alertMessages);
    expect(alerts).toEqual([]);
  });

  it("raises a CRITICAL device_down alert for a down asset", () => {
    const asset = baseAsset({ status: "down", hostname: "router-1" });

    const alerts = computeAlerts([asset], tr.alertMessages);

    expect(alerts).toHaveLength(1);
    expect(alerts[0].rule).toBe("device_down");
    expect(alerts[0].severity).toBe("CRITICAL");
    expect(alerts[0].message).toContain("router-1");
  });

  it("raises a WARNING high_latency alert above the threshold", () => {
    const asset = baseAsset({ latency_ms: 150 });

    const alerts = computeAlerts([asset], tr.alertMessages);

    expect(alerts).toHaveLength(1);
    expect(alerts[0].rule).toBe("high_latency");
    expect(alerts[0].severity).toBe("WARNING");
  });

  it("does not raise high_latency at or below the threshold", () => {
    const alerts = computeAlerts([baseAsset({ latency_ms: 100 })], tr.alertMessages);
    expect(alerts).toEqual([]);
  });

  it("raises a WARNING high_risk_port alert for each high-risk open port", () => {
    const asset = baseAsset({
      open_ports: [
        { port: 445, status: "open", latency_ms: 1 },
        { port: 80, status: "open", latency_ms: 1 },
        { port: 3389, status: "open", latency_ms: 1 },
      ],
    });

    const alerts = computeAlerts([asset], tr.alertMessages);

    const portAlerts = alerts.filter((a) => a.rule === "high_risk_port");
    expect(portAlerts).toHaveLength(2);
    expect(portAlerts.map((a) => a.message).join(" ")).toContain("445");
    expect(portAlerts.map((a) => a.message).join(" ")).toContain("3389");
  });

  it("never raises SNMP-based rules when no monitoring data is passed", () => {
    // Faz 26: gerçek bir SNMP veri kaynağı artık var (bkz.
    // `computeSnmpAlerts`), ama `options.monitoring` geçilmezse bu
    // kurallar yine de hiç tetiklenmez — uydurma alert yok.
    const alerts = computeAlerts(
      [baseAsset({ status: "down", latency_ms: 200 })],
      tr.alertMessages,
    );

    expect(alerts.some((a) => a.rule === "interface_down")).toBe(false);
    expect(alerts.some((a) => a.rule === "interface_error")).toBe(false);
    expect(alerts.some((a) => a.rule === "snmp_poll_failure")).toBe(false);
    expect(alerts.some((a) => a.rule === "device_unreachable")).toBe(false);
    expect(alerts.some((a) => a.rule === "high_bandwidth")).toBe(false);
    expect(alerts.some((a) => a.rule === "high_utilization")).toBe(false);
  });

  it("sorts alerts by severity (CRITICAL before WARNING)", () => {
    const alerts = computeAlerts(
      [
        baseAsset({ ip_address: "10.0.0.2", latency_ms: 200 }),
        baseAsset({ ip_address: "10.0.0.3", status: "down" }),
      ],
      tr.alertMessages,
    );

    expect(alerts[0].severity).toBe("CRITICAL");
    expect(alerts[1].severity).toBe("WARNING");
  });

  it("returns an empty list for an empty asset list", () => {
    expect(computeAlerts([], tr.alertMessages)).toEqual([]);
  });

  it("raises a CRITICAL high_latency alert above the critical threshold", () => {
    const asset = baseAsset({ latency_ms: 600 });

    const alerts = computeAlerts([asset], tr.alertMessages);

    expect(alerts).toHaveLength(1);
    expect(alerts[0].rule).toBe("high_latency");
    expect(alerts[0].severity).toBe("CRITICAL");
  });

  it("honors custom thresholds passed via options", () => {
    const alerts = computeAlerts([baseAsset({ latency_ms: 50 })], tr.alertMessages, {
      thresholds: { latencyWarningMs: 20 },
    });

    expect(alerts).toHaveLength(1);
    expect(alerts[0].rule).toBe("high_latency");
    expect(alerts[0].severity).toBe("WARNING");
  });
});

describe("computeAlerts — SNMP-based rules (Faz 26)", () => {
  it("raises a CRITICAL device_unreachable alert when SNMP status is unreachable", () => {
    const asset = baseAsset({ hostname: "core-sw-01" });
    const monitoring = { [asset.id]: pollResult(asset.id, { status: "unreachable", system: null }) };

    const alerts = computeAlerts([asset], tr.alertMessages, { monitoring });

    expect(alerts).toHaveLength(1);
    expect(alerts[0].rule).toBe("device_unreachable");
    expect(alerts[0].severity).toBe("CRITICAL");
  });

  it("raises a WARNING snmp_poll_failure alert on timeout/authentication_failed", () => {
    const asset = baseAsset();
    const timeoutResult = { [asset.id]: pollResult(asset.id, { status: "timeout", system: null }) };
    const authResult = { [asset.id]: pollResult(asset.id, { status: "authentication_failed", system: null }) };

    expect(computeAlerts([asset], tr.alertMessages, { monitoring: timeoutResult })[0].rule).toBe(
      "snmp_poll_failure",
    );
    expect(computeAlerts([asset], tr.alertMessages, { monitoring: authResult })[0].severity).toBe(
      "WARNING",
    );
  });

  it("does not raise device_unreachable/snmp_poll_failure on success or not_configured", () => {
    const asset = baseAsset();
    for (const status of ["success", "not_configured", "partial"] as const) {
      const monitoring = { [asset.id]: pollResult(asset.id, { status }) };
      const alerts = computeAlerts([asset], tr.alertMessages, { monitoring });
      expect(alerts.some((a) => a.rule === "device_unreachable" || a.rule === "snmp_poll_failure")).toBe(
        false,
      );
    }
  });

  it("raises interface_down only when admin=up and oper=down", () => {
    const asset = baseAsset();
    const monitoring = {
      [asset.id]: pollResult(asset.id, {
        interfaces: [
          baseInterface({ if_index: 1, if_admin_status: "up", if_oper_status: "down" }),
          baseInterface({ if_index: 2, if_admin_status: "down", if_oper_status: "down" }), // admin kapalı — beklenen, alert değil
          baseInterface({ if_index: 3, if_admin_status: "up", if_oper_status: "up" }),
        ],
      }),
    };

    const alerts = computeAlerts([asset], tr.alertMessages, { monitoring });
    const downAlerts = alerts.filter((a) => a.rule === "interface_down");

    expect(downAlerts).toHaveLength(1);
    expect(downAlerts[0].id).toContain(":1");
    expect(downAlerts[0].severity).toBe("WARNING");
  });

  it("raises interface_error when error counters are non-zero", () => {
    const asset = baseAsset();
    const monitoring = {
      [asset.id]: pollResult(asset.id, {
        interfaces: [baseInterface({ if_in_errors: 4, if_out_errors: 0 })],
      }),
    };

    const alerts = computeAlerts([asset], tr.alertMessages, { monitoring });

    expect(alerts).toHaveLength(1);
    expect(alerts[0].rule).toBe("interface_error");
    expect(alerts[0].message).toContain("4");
  });

  it("does not raise interface_error when error counters are null (unsupported by agent)", () => {
    const asset = baseAsset();
    const monitoring = {
      [asset.id]: pollResult(asset.id, {
        interfaces: [baseInterface({ if_in_errors: null, if_out_errors: null })],
      }),
    };

    const alerts = computeAlerts([asset], tr.alertMessages, { monitoring });
    expect(alerts.some((a) => a.rule === "interface_error")).toBe(false);
  });

  it("raises high_bandwidth when bps exceeds the configured threshold", () => {
    const asset = baseAsset();
    const monitoring = {
      [asset.id]: pollResult(asset.id, {
        interfaces: [baseInterface({ if_in_bps: 900_000_000, if_out_bps: 100 })],
      }),
    };

    const alerts = computeAlerts([asset], tr.alertMessages, { monitoring });
    const bwAlerts = alerts.filter((a) => a.rule === "high_bandwidth");

    expect(bwAlerts).toHaveLength(1);
    expect(bwAlerts[0].id).toContain(":in");
  });

  it("does not raise high_bandwidth when bps is null (no baseline yet — first poll)", () => {
    const asset = baseAsset();
    const monitoring = {
      [asset.id]: pollResult(asset.id, {
        interfaces: [baseInterface({ if_in_bps: null, if_out_bps: null })],
      }),
    };

    const alerts = computeAlerts([asset], tr.alertMessages, { monitoring });
    expect(alerts.some((a) => a.rule === "high_bandwidth")).toBe(false);
  });

  it("raises WARNING then CRITICAL high_utilization as utilization crosses thresholds", () => {
    const asset = baseAsset();
    const warningMonitoring = {
      [asset.id]: pollResult(asset.id, {
        interfaces: [baseInterface({ if_speed_bps: 1_000_000_000, if_in_bps: 750_000_000, if_out_bps: 0 })],
      }),
    };
    const criticalMonitoring = {
      [asset.id]: pollResult(asset.id, {
        interfaces: [baseInterface({ if_speed_bps: 1_000_000_000, if_in_bps: 950_000_000, if_out_bps: 0 })],
      }),
    };

    const warningAlerts = computeAlerts([asset], tr.alertMessages, { monitoring: warningMonitoring });
    const criticalAlerts = computeAlerts([asset], tr.alertMessages, { monitoring: criticalMonitoring });

    expect(warningAlerts.find((a) => a.rule === "high_utilization")?.severity).toBe("WARNING");
    expect(criticalAlerts.find((a) => a.rule === "high_utilization")?.severity).toBe("CRITICAL");
  });

  it("does not raise high_utilization when if_speed_bps is missing (no capacity data)", () => {
    const asset = baseAsset();
    const monitoring = {
      [asset.id]: pollResult(asset.id, {
        interfaces: [baseInterface({ if_speed_bps: null, if_in_bps: 900_000_000 })],
      }),
    };

    const alerts = computeAlerts([asset], tr.alertMessages, { monitoring });
    expect(alerts.some((a) => a.rule === "high_utilization")).toBe(false);
  });

  it("honors custom highBandwidthBps threshold", () => {
    const asset = baseAsset();
    const monitoring = {
      [asset.id]: pollResult(asset.id, {
        interfaces: [baseInterface({ if_in_bps: 5_000_000, if_out_bps: 0 })],
      }),
    };

    const noAlert = computeAlerts([asset], tr.alertMessages, { monitoring });
    const withAlert = computeAlerts([asset], tr.alertMessages, {
      monitoring,
      thresholds: { highBandwidthBps: 1_000_000 },
    });

    expect(noAlert.some((a) => a.rule === "high_bandwidth")).toBe(false);
    expect(withAlert.some((a) => a.rule === "high_bandwidth")).toBe(true);
  });
});
