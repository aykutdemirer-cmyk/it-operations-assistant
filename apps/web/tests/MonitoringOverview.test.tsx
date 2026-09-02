import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MonitoringOverview } from "@/components/MonitoringOverview";
import { tr } from "@/lib/i18n/translations";
import { mockAssetsAndScans, renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("MonitoringOverview", () => {
  it("shows the not-configured message when no real poll was attempted", async () => {
    mockAssetsAndScans([{ id: "1", status: "up" }], []);

    renderWithDashboardData(<MonitoringOverview />);

    expect(
      await screen.findByText(tr.monitoring.notConfiguredMessage),
    ).toBeInTheDocument();
  });

  it("shows 0% SNMP coverage and 0 monitored devices when the batch is empty — honest, not fabricated", async () => {
    mockAssetsAndScans(
      [
        { id: "1", status: "up" },
        { id: "2", status: "up" },
      ],
      [],
    );

    renderWithDashboardData(<MonitoringOverview />);

    expect(await screen.findByText("0%")).toBeInTheDocument();
    const monitoredLabel = await screen.findByText(tr.monitoring.monitoredDevices);
    const stat = monitoredLabel.parentElement as HTMLElement;
    expect(stat.querySelector('[class*="value"]')?.textContent).toBe("0");
  });

  it("shows real, non-zero coverage/monitored-device counts from GET /api/monitoring", async () => {
    mockAssetsAndScans(
      [
        { id: "1", ip_address: "10.0.9.1", hostname: "core-sw-01", status: "up" },
        { id: "2", ip_address: "10.0.9.2", hostname: null, status: "up" },
      ],
      [],
      {
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
            system: { sys_name: "core-sw-01", sys_descr: null, sys_object_id: null, sys_uptime_ticks: 100 },
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
      },
    );

    renderWithDashboardData(<MonitoringOverview />);

    expect(await screen.findByText("50%")).toBeInTheDocument();
    const monitoredLabel = await screen.findByText(tr.monitoring.monitoredDevices);
    const stat = monitoredLabel.parentElement as HTMLElement;
    expect(stat.querySelector('[class*="value"]')?.textContent).toBe("1");

    // Interface Monitoring + Bandwidth tabloları gerçek veriyi gösteriyor
    // ("core-sw-01" hem Interface Monitoring hem Recent Polls'ta geçer).
    expect(screen.getAllByText("core-sw-01").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Gi0/1").length).toBeGreaterThan(0);
    expect(screen.getByText("5.0 Mbps")).toBeInTheDocument();

    // Recent Polls tablosu yalnızca gerçekten denenen (not_configured
    // olmayan) poll'u gösteriyor.
    expect(screen.getByText(tr.monitoring.pollStatus.success)).toBeInTheDocument();
  });

  it("always shows explicit no-data text for cpu/memory regardless of monitoring data", async () => {
    mockAssetsAndScans([{ id: "1", status: "up" }], []);

    renderWithDashboardData(<MonitoringOverview />);

    expect(
      await screen.findByText(tr.monitoring.interfaceMonitoring),
    ).toBeInTheDocument();
    // Boş batch'te: interface + bandwidth + cpu + memory + recentPolls = 5.
    expect(screen.getAllByText(tr.monitoring.noData)).toHaveLength(5);
  });
});
