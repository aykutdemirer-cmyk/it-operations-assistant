import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InfrastructureHealth } from "@/components/InfrastructureHealth";
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

const UP_ASSET = { id: "1", status: "up" };
const DOWN_ASSET = { id: "2", status: "down" };

describe("InfrastructureHealth", () => {
  it("shows a loading state", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    renderWithDashboardData(<InfrastructureHealth />);

    expect(screen.getByText(tr.common.loading)).toBeInTheDocument();
  });

  it("shows 'No data available' when there are no assets", async () => {
    mockAssets([]);

    renderWithDashboardData(<InfrastructureHealth />);

    expect(
      await screen.findByText(`${tr.common.noDataAvailable}.`),
    ).toBeInTheDocument();
  });

  it("shows a real availability percentage computed from assets", async () => {
    mockAssets([UP_ASSET, UP_ASSET, UP_ASSET, DOWN_ASSET]);

    renderWithDashboardData(<InfrastructureHealth />);

    expect(await screen.findByText("75%")).toBeInTheDocument();
    expect(
      screen.getByText(new RegExp(`${tr.dashboard.health.online} 75% \\(3\\)`)),
    ).toBeInTheDocument();
    expect(
      screen.getByText(new RegExp(`${tr.dashboard.health.offline} 25% \\(1\\)`)),
    ).toBeInTheDocument();
  });

  it("shows an error state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) }),
    );

    renderWithDashboardData(<InfrastructureHealth />);

    expect(await screen.findByText(tr.common.unableToLoad)).toBeInTheDocument();
  });
});
