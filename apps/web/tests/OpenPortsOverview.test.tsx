import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OpenPortsOverview } from "@/components/OpenPortsOverview";
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

describe("OpenPortsOverview", () => {
  it("shows a loading state while the request is in flight", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    renderWithDashboardData(<OpenPortsOverview />);

    expect(screen.getByText(tr.common.loading)).toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) }),
    );

    renderWithDashboardData(<OpenPortsOverview />);

    expect(await screen.findByText(tr.common.unableToLoad)).toBeInTheDocument();
  });

  it("shows an empty state when there are no open ports", async () => {
    mockAssets([{ id: "1", open_ports: [] }]);

    renderWithDashboardData(<OpenPortsOverview />);

    expect(
      await screen.findByText(tr.dashboard.openPorts.noOpenPorts),
    ).toBeInTheDocument();
  });

  it("renders real ports with device counts and risk badges", async () => {
    mockAssets([
      { id: "1", open_ports: [{ port: 445, status: "open", latency_ms: 1 }] },
      { id: "2", open_ports: [{ port: 445, status: "open", latency_ms: 1 }] },
      { id: "3", open_ports: [{ port: 80, status: "open", latency_ms: 1 }] },
    ]);

    renderWithDashboardData(<OpenPortsOverview />);

    expect(await screen.findByText("445")).toBeInTheDocument();
    expect(screen.getByText(tr.risk.high)).toBeInTheDocument();
    expect(screen.getByText("80")).toBeInTheDocument();
    expect(screen.getByText(tr.risk.low)).toBeInTheDocument();
  });
});
