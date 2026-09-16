import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AlertsList } from "@/components/AlertsList";
import { tr } from "@/lib/i18n/translations";
import { mockAssetsAndScans, renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
});

const BASE_ASSET = {
  id: "1",
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
};

function mockAssets(assets: unknown[]) {
  mockAssetsAndScans(assets, []);
}

describe("AlertsList", () => {
  it("shows a no-alerts empty state", async () => {
    mockAssets([BASE_ASSET]);

    renderWithDashboardData(<AlertsList />);

    expect(await screen.findByText(tr.alerts.noAlerts)).toBeInTheDocument();
  });

  it("shows all real alerts by default", async () => {
    mockAssets([
      { ...BASE_ASSET, id: "down-1", status: "down", hostname: "router-1" },
      {
        ...BASE_ASSET,
        id: "risky-1",
        hostname: "server-1",
        open_ports: [{ port: 3389, status: "open", latency_ms: 1 }],
      },
    ]);

    renderWithDashboardData(<AlertsList />);

    expect(await screen.findByText(/router-1/)).toBeInTheDocument();
    expect(screen.getByText(/server-1/)).toBeInTheDocument();
  });

  it("filters by severity", async () => {
    mockAssets([
      { ...BASE_ASSET, id: "down-1", status: "down", hostname: "router-1" },
      {
        ...BASE_ASSET,
        id: "risky-1",
        hostname: "server-1",
        open_ports: [{ port: 3389, status: "open", latency_ms: 1 }],
      },
    ]);

    renderWithDashboardData(<AlertsList />);
    await screen.findByText(/router-1/);

    fireEvent.click(screen.getByRole("button", { name: tr.alerts.filterCritical }));

    expect(screen.getByText(/router-1/)).toBeInTheDocument();
    expect(screen.queryByText(/server-1/)).not.toBeInTheDocument();
  });

  it("filters by search text across device label and message", async () => {
    mockAssets([
      { ...BASE_ASSET, id: "down-1", status: "down", hostname: "router-1" },
      {
        ...BASE_ASSET,
        id: "risky-1",
        hostname: "server-1",
        open_ports: [{ port: 3389, status: "open", latency_ms: 1 }],
      },
    ]);

    renderWithDashboardData(<AlertsList />);
    await screen.findByText(/router-1/);

    fireEvent.change(screen.getByLabelText(tr.alerts.searchAriaLabel), {
      target: { value: "server-1" },
    });

    expect(screen.getByText(/server-1/)).toBeInTheDocument();
    expect(screen.queryByText(/router-1/)).not.toBeInTheDocument();
  });

  it("shows a no-match message when filters exclude every alert", async () => {
    mockAssets([{ ...BASE_ASSET, id: "down-1", status: "down", hostname: "router-1" }]);

    renderWithDashboardData(<AlertsList />);
    await screen.findByText(/router-1/);

    fireEvent.click(screen.getByRole("button", { name: tr.alerts.filterInfo }));

    expect(await screen.findByText(tr.alerts.noMatchFilters)).toBeInTheDocument();
  });

  it("renders a real SNMP interface_down alert once monitoring data is wired in (Faz 70)", async () => {
    mockAssetsAndScans([{ ...BASE_ASSET, hostname: "core-sw-01" }], [], undefined, [], [], {
      latest_batch: {
        started_at: "2026-09-11T00:00:00Z",
        completed_at: "2026-09-11T00:00:01Z",
        duration_ms: 10,
        total: 1,
        polled: 1,
        not_configured: 0,
        results: [
          {
            asset_id: "1",
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

    renderWithDashboardData(<AlertsList />);

    expect(await screen.findByText(/core-sw-01/)).toBeInTheDocument();
    expect(screen.getByText(tr.severity.warning)).toBeInTheDocument();
  });
});
