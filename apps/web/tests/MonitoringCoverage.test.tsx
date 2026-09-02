import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MonitoringCoverage } from "@/components/MonitoringCoverage";
import { tr } from "@/lib/i18n/translations";
import { mockAssetsAndScans, renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockAssets(assets: unknown[]) {
  mockAssetsAndScans(assets, []);
}

describe("MonitoringCoverage", () => {
  it("shows a loading state", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    renderWithDashboardData(<MonitoringCoverage />);

    expect(screen.getByText(tr.common.loading)).toBeInTheDocument();
  });

  it("shows 'No data available' when there are no assets", async () => {
    mockAssets([]);

    renderWithDashboardData(<MonitoringCoverage />);

    expect(
      await screen.findByText(`${tr.common.noDataAvailable}.`),
    ).toBeInTheDocument();
  });

  it("shows 0 SNMP-enabled devices when no profile is assigned to any asset", async () => {
    mockAssetsAndScans(
      [
        { id: "1", status: "up" },
        { id: "2", status: "down" },
      ],
      [],
    );

    renderWithDashboardData(<MonitoringCoverage />);

    const label = tr.dashboard.monitoringCoverage.snmpEnabled;
    await screen.findByText(label);
    const row = screen.getByText(label).parentElement as HTMLElement;
    expect(row.querySelector("dd")?.textContent).toBe("0");
  });

  it("reflects the real assigned SNMP profile count (Faz 29.5)", async () => {
    mockAssetsAndScans(
      [
        { id: "1", status: "up" },
        { id: "2", status: "up" },
        { id: "3", status: "down" },
      ],
      [],
      undefined,
      [
        { id: "p1", assigned_asset_count: 2 },
        { id: "p2", assigned_asset_count: 0 },
      ],
    );

    renderWithDashboardData(<MonitoringCoverage />);

    const enabledLabel = tr.dashboard.monitoringCoverage.snmpEnabled;
    await screen.findByText(enabledLabel);
    const enabledRow = screen.getByText(enabledLabel).parentElement as HTMLElement;
    expect(enabledRow.querySelector("dd")?.textContent).toBe("2");

    const disabledLabel = tr.dashboard.monitoringCoverage.snmpDisabled;
    const disabledRow = screen.getByText(disabledLabel).parentElement as HTMLElement;
    expect(disabledRow.querySelector("dd")?.textContent).toBe("1");
  });

  it("reports unreachable count from real down assets", async () => {
    mockAssets([
      { id: "1", status: "up" },
      { id: "2", status: "down" },
      { id: "3", status: "down" },
    ]);

    renderWithDashboardData(<MonitoringCoverage />);

    const label = tr.dashboard.monitoringCoverage.unreachable;
    await screen.findByText(label);
    const row = screen.getByText(label).parentElement as HTMLElement;
    expect(row.querySelector("dd")?.textContent).toBe("2");
  });

  it("shows an error state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) }),
    );

    renderWithDashboardData(<MonitoringCoverage />);

    expect(await screen.findByText(tr.common.unableToLoad)).toBeInTheDocument();
  });
});
