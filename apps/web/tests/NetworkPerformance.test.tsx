import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NetworkPerformance } from "@/components/NetworkPerformance";
import { tr } from "@/lib/i18n/translations";
import { mockAssetsAndScans, renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("NetworkPerformance", () => {
  it("shows a loading state while assets are in flight", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    renderWithDashboardData(<NetworkPerformance />);

    expect(screen.getByText(tr.common.loading)).toBeInTheDocument();
  });

  it("always shows explicit no-data text for Network Load and Top Talkers — no SNMP data exists", async () => {
    mockAssetsAndScans([{ id: "1", status: "up" }], []);

    const n = tr.dashboard.networkPerformance;
    renderWithDashboardData(<NetworkPerformance />);

    expect(await screen.findByText(n.networkLoad)).toBeInTheDocument();
    expect(screen.getByText(n.topTalkers)).toBeInTheDocument();
    expect(screen.getAllByText(n.noInterfaceData)).toHaveLength(2);
  });

  it("shows no-data sections even with zero assets — never fabricates a metric", async () => {
    mockAssetsAndScans([], []);

    renderWithDashboardData(<NetworkPerformance />);

    expect(
      await screen.findAllByText(tr.dashboard.networkPerformance.noInterfaceData),
    ).toHaveLength(2);
  });
});
