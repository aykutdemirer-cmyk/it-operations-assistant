import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MonitoringOverview } from "@/components/MonitoringOverview";
import { tr } from "@/lib/i18n/translations";
import { mockAssetsAndScans, renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
});

const SYSTEM_INFO = {
  sys_name: "core-sw-01",
  sys_descr: null,
  sys_object_id: null,
  sys_uptime_ticks: 100,
  cpu_percent: null,
  memory_used_bytes: null,
  memory_total_bytes: null,
};

const LATEST_BATCH = {
  started_at: "2026-08-26T00:00:00Z",
  completed_at: "2026-08-26T00:00:01Z",
  duration_ms: 120,
  total: 2,
  polled: 1,
  not_configured: 1,
  results: [
    {
      asset_id: "1",
      polled_at: "2026-08-26T00:00:00Z",
      status: "success",
      system: SYSTEM_INFO,
      interfaces: [
        {
          if_index: 1,
          if_name: "Gi0/1",
          if_descr: "GigabitEthernet0/1",
          if_admin_status: "up",
          if_oper_status: "up",
          if_speed_bps: 1_000_000_000,
          if_in_octets: 1000,
          if_out_octets: 2000,
          if_counters_64bit: true,
          if_in_bps: 5_000_000,
          if_out_bps: 2_000_000,
          if_in_errors: 0,
          if_out_errors: 0,
        },
      ],
      error: null,
      duration_ms: 42,
    },
    {
      asset_id: "2",
      polled_at: "2026-08-26T00:00:00Z",
      status: "not_configured",
      system: null,
      interfaces: [],
      error: "SNMP credential/community bu asset için henüz yapılandırılmadı.",
      duration_ms: null,
    },
  ],
};

const HISTORY_WITH_DATA = {
  latest_batch: LATEST_BATCH,
  poll_log: [
    { asset_id: "1", status: "success", duration_ms: 42, oid_count: 13, polled_at: "2026-08-26T00:00:00Z", error: null },
    { asset_id: "2", status: "not_configured", duration_ms: null, oid_count: 0, polled_at: "2026-08-26T00:00:00Z", error: "not configured" },
  ],
  bandwidth_history: [
    { ts: "2026-08-26T00:00:00Z", total_in_bps: 5_000_000, total_out_bps: 2_000_000 },
  ],
};

const EMPTY_HISTORY = { latest_batch: null, poll_log: [], bandwidth_history: [] };

describe("MonitoringOverview", () => {
  it("shows a waiting notice when the background poller hasn't run yet", async () => {
    mockAssetsAndScans([{ id: "1", status: "up" }], [], undefined, [], [], EMPTY_HISTORY);

    renderWithDashboardData(<MonitoringOverview />);

    expect(await screen.findByText(tr.monitoring.waitingForFirstPoll)).toBeInTheDocument();
  });

  it("shows real, non-fabricated coverage/monitored-device counts from GET /api/monitoring/history", async () => {
    mockAssetsAndScans(
      [
        { id: "1", ip_address: "10.0.9.1", hostname: "core-sw-01", status: "up" },
        { id: "2", ip_address: "10.0.9.2", hostname: null, status: "up" },
      ],
      [],
      undefined,
      [],
      [],
      HISTORY_WITH_DATA,
    );

    renderWithDashboardData(<MonitoringOverview />);

    expect(await screen.findByText("50%")).toBeInTheDocument();
    expect(await screen.findByText(tr.monitoring.kpi.monitoredDevices)).toBeInTheDocument();

    // Arayüz tablosu + poll log gerçek veriyi gösteriyor.
    expect(screen.getAllByText("core-sw-01").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Gi0/1").length).toBeGreaterThan(0);
    expect(screen.getByText("5.0 Mbps")).toBeInTheDocument();
    expect(screen.getByText(tr.monitoring.pollStatus.success)).toBeInTheDocument();
  });

  it("shows the real total bandwidth KPI from the latest aggregated sample", async () => {
    mockAssetsAndScans([{ id: "1", status: "up" }], [], undefined, [], [], HISTORY_WITH_DATA);

    renderWithDashboardData(<MonitoringOverview />);

    expect(await screen.findByText("↓5.0 / ↑2.0 Mbps")).toBeInTheDocument();
  });

  it("shows a real average latency KPI derived from real asset ping data — no data means an honest placeholder", async () => {
    mockAssetsAndScans(
      [
        { id: "1", status: "up", latency_ms: 10 },
        { id: "2", status: "up", latency_ms: 20 },
      ],
      [],
      undefined,
      [],
      [],
      HISTORY_WITH_DATA,
    );

    renderWithDashboardData(<MonitoringOverview />);

    expect(await screen.findByText("15 ms")).toBeInTheDocument();
  });

  it("shows an honest placeholder for average latency when no asset has ping data", async () => {
    mockAssetsAndScans([{ id: "1", status: "up", latency_ms: null }], [], undefined, [], [], HISTORY_WITH_DATA);

    renderWithDashboardData(<MonitoringOverview />);

    expect(await screen.findByText(tr.monitoring.kpi.noLatencyData)).toBeInTheDocument();
  });

  it("shows the poll log stream with device, status, duration, and OID count", async () => {
    mockAssetsAndScans([{ id: "1", status: "up" }], [], undefined, [], [], HISTORY_WITH_DATA);

    renderWithDashboardData(<MonitoringOverview />);

    await screen.findByText(tr.monitoring.pollLog.title);
    expect(screen.getByText("13")).toBeInTheDocument();
    expect(screen.getByText("42ms")).toBeInTheDocument();
  });

  it("shows an honest empty state for the interface table and poll log when nothing has been polled yet", async () => {
    mockAssetsAndScans([{ id: "1", status: "up" }], [], undefined, [], [], EMPTY_HISTORY);

    renderWithDashboardData(<MonitoringOverview />);

    await screen.findByText(tr.monitoring.interfaceTable.title);
    expect(screen.getAllByText(tr.monitoring.noData).length).toBeGreaterThan(0);
    expect(screen.getByText(tr.monitoring.pollLog.empty)).toBeInTheDocument();
  });
});
