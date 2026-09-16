import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DeviceHealthSummary } from "@/components/DeviceHealthSummary";
import { tr } from "@/lib/i18n/translations";
import { mockAssetsAndScans, renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockAssets(assets: unknown[]) {
  mockAssetsAndScans(assets, []);
}

const DOWN_ASSET = { id: "1", status: "down", open_ports: [] };
const UP_HIGH_RISK_ASSET = {
  id: "2",
  status: "up",
  open_ports: [{ port: 3389, status: "open", latency_ms: 1 }],
};
const UP_HEALTHY_ASSET = { id: "3", status: "up", open_ports: [] };

describe("DeviceHealthSummary", () => {
  it("shows a loading state", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    renderWithDashboardData(<DeviceHealthSummary />);

    expect(screen.getByText(tr.common.loading)).toBeInTheDocument();
  });

  it("shows 'No data available' when there are no assets", async () => {
    mockAssets([]);

    renderWithDashboardData(<DeviceHealthSummary />);

    expect(
      await screen.findByText(`${tr.common.noDataAvailable}.`),
    ).toBeInTheDocument();
  });

  it("classifies devices into Critical/Warning/Healthy from real data, shown as colored pill labels", async () => {
    mockAssets([DOWN_ASSET, UP_HIGH_RISK_ASSET, UP_HEALTHY_ASSET]);

    const d = tr.dashboard.deviceHealth;
    renderWithDashboardData(<DeviceHealthSummary />);

    expect(await screen.findByText(`${d.critical}: 1`)).toBeInTheDocument();
    expect(screen.getByText(`${d.warning}: 1`)).toBeInTheDocument();
    expect(screen.getByText(`${d.healthy}: 1`)).toBeInTheDocument();
  });

  it("shows unmonitored equal to the total asset count", async () => {
    mockAssets([DOWN_ASSET, UP_HIGH_RISK_ASSET, UP_HEALTHY_ASSET]);

    renderWithDashboardData(<DeviceHealthSummary />);

    expect(await screen.findByText(`${tr.dashboard.deviceHealth.unmonitored}: 3`)).toBeInTheDocument();
  });

  it("counts a real SNMP interface_down alert as Warning once monitoring data is wired in (Faz 70)", async () => {
    mockAssetsAndScans([UP_HEALTHY_ASSET], [], undefined, [], [], {
      latest_batch: {
        started_at: "2026-09-11T00:00:00Z",
        completed_at: "2026-09-11T00:00:01Z",
        duration_ms: 10,
        total: 1,
        polled: 1,
        not_configured: 0,
        results: [
          {
            asset_id: "3",
            polled_at: "2026-09-11T00:00:00Z",
            status: "success",
            system: null,
            interfaces: [
              {
                if_index: 1,
                if_name: "Gi0/1",
                if_descr: null,
                if_admin_status: "up",
                if_oper_status: "down",
                if_speed_bps: null,
                if_in_octets: null,
                if_out_octets: null,
                if_counters_64bit: null,
                if_in_bps: null,
                if_out_bps: null,
                if_in_errors: null,
                if_out_errors: null,
              },
            ],
            error: null,
            duration_ms: 5,
          },
        ],
      },
      poll_log: [],
      bandwidth_history: [],
    });

    const d = tr.dashboard.deviceHealth;
    renderWithDashboardData(<DeviceHealthSummary />);

    expect(await screen.findByText(`${d.warning}: 1`)).toBeInTheDocument();
    expect(screen.getByText(`${d.healthy}: 0`)).toBeInTheDocument();
  });

  it("shows an error state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) }),
    );

    renderWithDashboardData(<DeviceHealthSummary />);

    expect(await screen.findByText(tr.common.unableToLoad)).toBeInTheDocument();
  });
});
