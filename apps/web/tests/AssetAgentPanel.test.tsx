import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssetAgentPanel } from "@/components/AssetAgentPanel";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPanel(assetId = "asset-1") {
  return render(
    <LocaleProvider>
      <AssetAgentPanel assetId={assetId} />
    </LocaleProvider>,
  );
}

describe("AssetAgentPanel", () => {
  it("shows 'no agent connected' when nothing links to this asset", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
    renderPanel();

    expect(await screen.findByText(tr.assetDetails.agent.notConnected)).toBeInTheDocument();
  });

  it("shows the linked agent's real status and version", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          {
            id: "agent-1", hostname: "h", os: "windows", os_version: "Server 2022",
            agent_version: "1.2.3", asset_id: "asset-1", status: "online",
            registered_at: "2026-01-01T00:00:00Z", last_heartbeat_at: new Date().toISOString(),
          },
        ],
      }),
    );
    renderPanel("asset-1");

    expect(await screen.findByText(tr.agents.statusLabels.online)).toBeInTheDocument();
    expect(screen.getByText("1.2.3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: new RegExp(tr.assetDetails.agent.viewDetails) })).toHaveAttribute(
      "href",
      "/agents/agent-1",
    );
  });

  it("ignores agents linked to a different asset", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          {
            id: "agent-1", hostname: "h", os: "windows", os_version: null,
            agent_version: "1.0.0", asset_id: "some-other-asset", status: "online",
            registered_at: "2026-01-01T00:00:00Z", last_heartbeat_at: null,
          },
        ],
      }),
    );
    renderPanel("asset-1");

    expect(await screen.findByText(tr.assetDetails.agent.notConnected)).toBeInTheDocument();
  });
});
