import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentHealthSummary } from "@/components/AgentHealthSummary";
import { tr } from "@/lib/i18n/translations";
import { renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockAgents(agents: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.includes("/api/agents")) {
        return Promise.resolve({ ok: true, json: async () => agents });
      }
      return Promise.resolve({ ok: true, json: async () => [] });
    }),
  );
}

describe("AgentHealthSummary", () => {
  it("shows the empty state when no agents are registered", async () => {
    mockAgents([]);
    renderWithDashboardData(<AgentHealthSummary />);

    expect(await screen.findByText(tr.dashboard.agentHealth.noAgents)).toBeInTheDocument();
  });

  it("reports real online/offline/unknown counts", async () => {
    mockAgents([
      { id: "1", hostname: "a", os: "linux", os_version: null, agent_version: "1.0.0", asset_id: null, status: "online", registered_at: "2026-01-01T00:00:00Z", last_heartbeat_at: null },
      { id: "2", hostname: "b", os: "linux", os_version: null, agent_version: "1.0.0", asset_id: null, status: "offline", registered_at: "2026-01-01T00:00:00Z", last_heartbeat_at: null },
    ]);
    renderWithDashboardData(<AgentHealthSummary />);

    const onlineLabel = await screen.findByText(tr.dashboard.agentHealth.online);
    expect(onlineLabel.parentElement?.parentElement?.querySelector("dd")?.textContent).toBe("1");
  });

  it("shows an error state when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) }));
    renderWithDashboardData(<AgentHealthSummary />);

    expect(await screen.findByText(tr.common.unableToLoad)).toBeInTheDocument();
  });
});
