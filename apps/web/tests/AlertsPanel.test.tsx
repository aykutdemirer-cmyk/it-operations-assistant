import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AlertsPanel } from "@/components/AlertsPanel";
import { tr } from "@/lib/i18n/translations";
import { renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockAssets(assets: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => assets }),
  );
}

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

describe("AlertsPanel", () => {
  it("shows a loading state while the request is in flight", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    renderWithDashboardData(<AlertsPanel />);

    expect(screen.getByText(tr.common.loading)).toBeInTheDocument();
  });

  it("shows a no-active-alerts empty state when nothing is wrong", async () => {
    mockAssets([BASE_ASSET]);

    renderWithDashboardData(<AlertsPanel />);

    expect(
      await screen.findByText(tr.dashboard.alertsPanel.noActiveAlerts),
    ).toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) }),
    );

    renderWithDashboardData(<AlertsPanel />);

    expect(await screen.findByText(tr.common.unableToLoad)).toBeInTheDocument();
  });

  it("renders a real device_down alert with CRITICAL severity", async () => {
    mockAssets([{ ...BASE_ASSET, status: "down", hostname: "core-router" }]);

    renderWithDashboardData(<AlertsPanel />);

    expect(await screen.findByText(tr.severity.critical)).toBeInTheDocument();
    expect(screen.getByText(/core-router/)).toBeInTheDocument();
  });

  it("renders a real high_risk_port alert with WARNING severity", async () => {
    mockAssets([
      { ...BASE_ASSET, open_ports: [{ port: 3389, status: "open", latency_ms: 1 }] },
    ]);

    renderWithDashboardData(<AlertsPanel />);

    expect(await screen.findByText(tr.severity.warning)).toBeInTheDocument();
    expect(screen.getByText(/3389/)).toBeInTheDocument();
  });

  it("shows a real Critical/Warning/Info alert overview count", async () => {
    mockAssets([
      { ...BASE_ASSET, id: "down-1", status: "down" },
      {
        ...BASE_ASSET,
        id: "risky-1",
        open_ports: [{ port: 445, status: "open", latency_ms: 1 }],
      },
    ]);

    renderWithDashboardData(<AlertsPanel />);

    expect(
      await screen.findByText(`1 ${tr.severity.critical}`),
    ).toBeInTheDocument();
    expect(screen.getByText(`1 ${tr.severity.warning}`)).toBeInTheDocument();
    expect(screen.getByText(`0 ${tr.severity.info}`)).toBeInTheDocument();
  });

  it("does not show an alert overview count when there are no alerts", async () => {
    mockAssets([BASE_ASSET]);

    renderWithDashboardData(<AlertsPanel />);

    await screen.findByText(tr.dashboard.alertsPanel.noActiveAlerts);
    expect(
      screen.queryByText(new RegExp(`${tr.severity.critical}$`)),
    ).not.toBeInTheDocument();
  });
});
