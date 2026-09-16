import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentsList } from "@/components/AgentsList";
import { tr } from "@/lib/i18n/translations";
import { mockAssetsAndScans, renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
});

const ONLINE_AGENT = {
  id: "11111111-1111-1111-1111-111111111111",
  hostname: "win-server-01",
  os: "windows",
  os_version: "Windows Server 2022",
  agent_version: "1.0.0",
  local_ip: "10.0.213.30",
  asset_id: null,
  status: "online",
  registered_at: "2026-08-28T00:00:00Z",
  last_heartbeat_at: new Date().toISOString(),
};

const OFFLINE_AGENT = {
  id: "22222222-2222-2222-2222-222222222222",
  hostname: "linux-db-01",
  os: "linux",
  os_version: "Ubuntu 24.04",
  agent_version: "1.0.0",
  local_ip: "10.0.213.5",
  asset_id: "asset-1",
  status: "offline",
  registered_at: "2026-08-28T00:00:00Z",
  last_heartbeat_at: "2026-08-27T00:00:00Z",
};

const LINKED_ASSET = {
  id: "asset-1",
  ip_address: "10.0.213.5",
  hostname: "db-host",
  mac_address: null,
  vendor: null,
  device_type: "server",
  confidence: "high",
  evidence: [],
  open_ports: [],
  status: "up",
  latency_ms: null,
  last_seen: "2026-08-28T00:00:00Z",
  created_at: "2026-08-28T00:00:00Z",
  updated_at: "2026-08-28T00:00:00Z",
};

describe("AgentsList", () => {
  it("shows the empty state when no agents are registered", async () => {
    mockAssetsAndScans([], [], undefined, [], []);
    renderWithDashboardData(<AgentsList />);

    expect(await screen.findByText(tr.agents.emptyTitle)).toBeInTheDocument();
  });

  it("renders a registered agent with its real status and hostname", async () => {
    mockAssetsAndScans([], [], undefined, [], [ONLINE_AGENT]);
    renderWithDashboardData(<AgentsList />);

    expect(await screen.findByText("win-server-01")).toBeInTheDocument();
    expect(screen.getByText(tr.agents.statusLabels.online)).toBeInTheDocument();
  });

  it("shows 'not linked' for an agent without an asset match", async () => {
    mockAssetsAndScans([], [], undefined, [], [ONLINE_AGENT]);
    renderWithDashboardData(<AgentsList />);

    const row = (await screen.findByText("win-server-01")).closest("tr") as HTMLElement;
    expect(within(row).getByText(tr.agents.noAssetLinked)).toBeInTheDocument();
  });

  it("resolves and shows the linked asset's hostname", async () => {
    mockAssetsAndScans([LINKED_ASSET], [], undefined, [], [OFFLINE_AGENT]);
    renderWithDashboardData(<AgentsList />);

    const row = (await screen.findByText("linux-db-01")).closest("tr") as HTMLElement;
    expect(within(row).getByText("db-host")).toBeInTheDocument();
    expect(within(row).getByText("10.0.213.5")).toBeInTheDocument();
  });

  it("links to the agent detail page", async () => {
    mockAssetsAndScans([], [], undefined, [], [ONLINE_AGENT]);
    renderWithDashboardData(<AgentsList />);

    await screen.findByText("win-server-01");
    expect(screen.getByRole("link", { name: tr.agents.view })).toHaveAttribute(
      "href",
      "/agents/11111111-1111-1111-1111-111111111111",
    );
  });

  it("filters agents by search text", async () => {
    mockAssetsAndScans([LINKED_ASSET], [], undefined, [], [ONLINE_AGENT, OFFLINE_AGENT]);
    renderWithDashboardData(<AgentsList />);

    await screen.findByText("win-server-01");
    fireEvent.change(screen.getByLabelText(tr.assets.searchAriaLabel), {
      target: { value: "linux" },
    });

    expect(screen.getByText("linux-db-01")).toBeInTheDocument();
    expect(screen.queryByText("win-server-01")).not.toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/api/agents")) {
          return Promise.resolve({ ok: false, status: 503, json: async () => ({}) });
        }
        return Promise.resolve({ ok: true, json: async () => [] });
      }),
    );
    renderWithDashboardData(<AgentsList />);

    expect(await screen.findByText(tr.agents.loadError)).toBeInTheDocument();
  });

  // --- Lifecycle Management ---

  it("opens the delete confirmation modal and archives the agent on confirm", async () => {
    mockAssetsAndScans([], [], undefined, [], [ONLINE_AGENT]);
    renderWithDashboardData(<AgentsList />);
    await screen.findByText("win-server-01");

    fireEvent.click(screen.getByRole("button", { name: tr.agents.delete }));

    expect(await screen.findByText(tr.agents.deleteModal.title)).toBeInTheDocument();

    const fetchMock = vi.mocked(global.fetch);
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve({ ok: true, json: async () => ({ archived: true, uninstall_command_id: null }) } as Response),
    );
    fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: tr.agents.deleteModal.confirm }));

    await waitFor(() => {
      const deleteCall = fetchMock.mock.calls.find(([url]) => String(url).includes("/api/agents/") && String(url).includes("send_uninstall_command"));
      expect(deleteCall).toBeTruthy();
    });
  });

  it("delete modal defaults the uninstall checkbox to unchecked", async () => {
    mockAssetsAndScans([], [], undefined, [], [ONLINE_AGENT]);
    renderWithDashboardData(<AgentsList />);
    await screen.findByText("win-server-01");

    fireEvent.click(screen.getByRole("button", { name: tr.agents.delete }));
    await screen.findByText(tr.agents.deleteModal.title);

    const checkbox = screen.getByLabelText(tr.agents.deleteModal.sendUninstallLabel) as HTMLInputElement;
    expect(checkbox.checked).toBe(false);
  });

  it("cancels the delete modal without calling the API", async () => {
    mockAssetsAndScans([], [], undefined, [], [ONLINE_AGENT]);
    renderWithDashboardData(<AgentsList />);
    await screen.findByText("win-server-01");

    fireEvent.click(screen.getByRole("button", { name: tr.agents.delete }));
    await screen.findByText(tr.agents.deleteModal.title);
    fireEvent.click(screen.getByRole("button", { name: tr.agents.deleteModal.cancel }));

    expect(screen.queryByText(tr.agents.deleteModal.title)).not.toBeInTheDocument();
  });

  it("shows an update badge and update button when a newer version is available", async () => {
    const updatable = { ...ONLINE_AGENT, update_available: true, latest_available_version: "2.0.0" };
    mockAssetsAndScans([], [], undefined, [], [updatable]);
    renderWithDashboardData(<AgentsList />);

    await screen.findByText("win-server-01");
    expect(screen.getByText(tr.agents.updateAvailable)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: tr.agents.update })).toBeInTheDocument();
  });

  it("does not show an update badge when no newer version is available", async () => {
    mockAssetsAndScans([], [], undefined, [], [ONLINE_AGENT]);
    renderWithDashboardData(<AgentsList />);

    await screen.findByText("win-server-01");
    expect(screen.queryByText(tr.agents.updateAvailable)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: tr.agents.update })).not.toBeInTheDocument();
  });

  it("switches to the archived tab and shows its empty state", async () => {
    mockAssetsAndScans([], [], undefined, [], [ONLINE_AGENT]);
    renderWithDashboardData(<AgentsList />);
    await screen.findByText("win-server-01");

    fireEvent.click(screen.getByRole("button", { name: tr.agents.tabs.archived }));

    expect(await screen.findByText(tr.agents.archived.emptyTitle)).toBeInTheDocument();
    expect(screen.queryByText("win-server-01")).not.toBeInTheDocument();
  });
});
