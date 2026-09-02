import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DeviceDistribution } from "@/components/DeviceDistribution";
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

describe("DeviceDistribution", () => {
  it("shows a loading state", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    renderWithDashboardData(<DeviceDistribution />);

    expect(screen.getByText(tr.common.loading)).toBeInTheDocument();
  });

  it("shows an empty state when there are no assets", async () => {
    mockAssets([]);

    renderWithDashboardData(<DeviceDistribution />);

    expect(
      await screen.findByText(tr.dashboard.deviceDistribution.noAssets),
    ).toBeInTheDocument();
  });

  it("computes a real distribution grouped by device type", async () => {
    mockAssets([
      { id: "1", device_type: "firewall" },
      { id: "2", device_type: "server" },
      { id: "3", device_type: "server" },
      { id: "4", device_type: "server" },
    ]);

    renderWithDashboardData(<DeviceDistribution />);

    expect(await screen.findByText(tr.deviceType.server)).toBeInTheDocument();
    expect(screen.getByText("3 (75%)")).toBeInTheDocument();
    expect(screen.getByText(tr.deviceType.firewall)).toBeInTheDocument();
    expect(screen.getByText("1 (25%)")).toBeInTheDocument();
  });

  it("only shows device types that are actually present", async () => {
    mockAssets([{ id: "1", device_type: "router" }]);

    renderWithDashboardData(<DeviceDistribution />);

    await screen.findByText(tr.deviceType.router);
    expect(screen.queryByText(tr.deviceType.printer)).not.toBeInTheDocument();
    expect(screen.queryByText(tr.deviceType.camera)).not.toBeInTheDocument();
  });
});
