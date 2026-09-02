import type { ReactElement } from "react";
import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

let mockSearchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useSearchParams: () => mockSearchParams,
}));

// `@xyflow/react` gerçek bir canvas/measurement katmanı kullanır (dagre
// benzeri layout, ResizeObserver) — jsdom'da bunu simüle etmek gereksiz
// karmaşıklık. Test SADECE bu projenin kendi mantığını (node içerikleri,
// tıklama → seçim, filtreler, istatistikler) doğrular, React Flow'un
// kendi pan/zoom/fit-view davranışını DEĞİL — bkz. tests/SshTerminal.test.tsx
// için aynı desen (xterm.js mock'u).
type MockNode = { id: string; type: string; data: unknown; selected?: boolean };
type MockReactFlowProps = {
  nodes: MockNode[];
  edges: unknown[];
  nodeTypes: Record<string, (props: { id: string; data: unknown; selected?: boolean }) => ReactElement>;
  onNodeClick?: (event: unknown, node: MockNode) => void;
};

vi.mock("@xyflow/react", () => {
  return {
    ReactFlow: ({ nodes, edges, nodeTypes, onNodeClick }: MockReactFlowProps) => (
      <div data-testid="react-flow-mock" data-edge-count={edges.length}>
        {nodes.map((node) => {
          const NodeComponent = nodeTypes[node.type];
          return (
            <div
              key={node.id}
              role="button"
              tabIndex={0}
              onClick={(event) => onNodeClick?.(event, node)}
            >
              <NodeComponent id={node.id} data={node.data} selected={node.selected} />
            </div>
          );
        })}
      </div>
    ),
    Background: () => null,
    Controls: () => null,
    Handle: () => null,
    Position: { Top: "top", Bottom: "bottom" },
  };
});

import { NetworkTopology } from "@/components/NetworkTopology";
import { tr } from "@/lib/i18n/translations";
import { mockAssetsAndScans, renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  mockSearchParams = new URLSearchParams();
});

const FIREWALL_ASSET = {
  id: "11111111-1111-1111-1111-111111111111",
  ip_address: "10.0.5.1",
  hostname: "firewall.example.local",
  mac_address: "AA-BB-CC-DD-EE-FF",
  vendor: "Fortinet, Inc.",
  device_type: "firewall",
  confidence: "high",
  evidence: ["vendor: Fortinet"],
  open_ports: [{ port: 443, status: "open", latency_ms: 2.4 }],
  status: "up",
  latency_ms: 2.1,
  last_seen: "2026-08-26T10:00:00Z",
  created_at: "2026-08-26T09:00:00Z",
  updated_at: "2026-08-26T10:00:00Z",
};

const DOWN_SERVER_ASSET = {
  id: "22222222-2222-2222-2222-222222222222",
  ip_address: "10.0.5.2",
  hostname: null,
  mac_address: null,
  vendor: null,
  device_type: "server",
  confidence: "low",
  evidence: [],
  open_ports: [],
  status: "down",
  latency_ms: null,
  last_seen: "2026-08-26T08:00:00Z",
  created_at: "2026-08-26T07:00:00Z",
  updated_at: "2026-08-26T08:00:00Z",
};

function mockFetchAssetsOnce(assets: unknown[]) {
  mockAssetsAndScans(assets, []);
}

describe("NetworkTopology", () => {
  it("shows an empty state when there are no assets", async () => {
    mockFetchAssetsOnce([]);

    renderWithDashboardData(<NetworkTopology />);

    expect(await screen.findByText(tr.topology.emptyTitle)).toBeInTheDocument();
  });

  it("renders each real asset as a node with its hostname/IP", async () => {
    mockFetchAssetsOnce([FIREWALL_ASSET, DOWN_SERVER_ASSET]);

    renderWithDashboardData(<NetworkTopology />);

    expect(await screen.findByText("firewall.example.local")).toBeInTheDocument();
    expect(screen.getAllByText("10.0.5.2").length).toBeGreaterThan(0);
  });

  it("shows the device type and status in the node title (no fabricated 'unknown' markers)", async () => {
    mockFetchAssetsOnce([FIREWALL_ASSET]);

    renderWithDashboardData(<NetworkTopology />);

    const label = await screen.findByText("firewall.example.local");
    const node = label.closest('[role="button"]');
    const iconWrap = (node as HTMLElement).querySelector("[title]");
    expect(iconWrap?.getAttribute("title")).toContain(tr.deviceType.firewall);
    expect(iconWrap?.getAttribute("title")).toContain("firewall.example.local");
  });

  it("opens the asset details panel when a node is clicked", async () => {
    mockFetchAssetsOnce([FIREWALL_ASSET]);

    renderWithDashboardData(<NetworkTopology />);

    const label = await screen.findByText("firewall.example.local");
    fireEvent.click(label.closest('[role="button"]') as HTMLElement);

    const panel = screen.getByLabelText(tr.assetDetails.ariaLabel);
    fireEvent.click(
      within(panel).getByRole("tab", { name: tr.assetDetails.tabs.network }),
    );
    expect(within(panel).getByText("AA-BB-CC-DD-EE-FF")).toBeInTheDocument();
  });

  it("renders the graph inside its own container", async () => {
    mockFetchAssetsOnce([FIREWALL_ASSET]);

    renderWithDashboardData(<NetworkTopology />);

    await screen.findByText("firewall.example.local");
    expect(screen.getByTestId("react-flow-mock")).toBeInTheDocument();
  });

  it("shows the not-fabricated connections note", async () => {
    mockFetchAssetsOnce([FIREWALL_ASSET]);

    renderWithDashboardData(<NetworkTopology />);

    expect(
      await screen.findByText(new RegExp(tr.topology.connectionsNote.slice(0, 20))),
    ).toBeInTheDocument();
  });

  it("shows a real, non-placeholder connections count in the stats row", async () => {
    mockFetchAssetsOnce([FIREWALL_ASSET, DOWN_SERVER_ASSET]);

    renderWithDashboardData(<NetworkTopology />);
    await screen.findByText("firewall.example.local");

    // both assets share the same /24 subnet -> single hub -> 2 edges
    const connectionsStat = screen.getByText(tr.topology.stats.connections).closest("div");
    expect(within(connectionsStat as HTMLElement).getByText("2")).toBeInTheDocument();
  });

  it("filters nodes by search text across ip, hostname, mac, and vendor", async () => {
    mockFetchAssetsOnce([FIREWALL_ASSET, DOWN_SERVER_ASSET]);

    renderWithDashboardData(<NetworkTopology />);
    await screen.findByText("firewall.example.local");

    fireEvent.change(screen.getByLabelText(tr.topology.searchAriaLabel), {
      target: { value: "10.0.5.2" },
    });

    expect(screen.queryByText("firewall.example.local")).not.toBeInTheDocument();
    expect(screen.getAllByText("10.0.5.2").length).toBeGreaterThan(0);
  });

  it("filters nodes by status", async () => {
    mockFetchAssetsOnce([FIREWALL_ASSET, DOWN_SERVER_ASSET]);

    renderWithDashboardData(<NetworkTopology />);
    await screen.findByText("firewall.example.local");

    fireEvent.change(screen.getByLabelText(tr.topology.filterByStatus), {
      target: { value: "down" },
    });

    expect(screen.queryByText("firewall.example.local")).not.toBeInTheDocument();
    expect(screen.getAllByText("10.0.5.2").length).toBeGreaterThan(0);
  });

  it("filters nodes by device type", async () => {
    mockFetchAssetsOnce([FIREWALL_ASSET, DOWN_SERVER_ASSET]);

    renderWithDashboardData(<NetworkTopology />);
    await screen.findByText("firewall.example.local");

    fireEvent.change(screen.getByLabelText(tr.topology.filterByDeviceType), {
      target: { value: "server" },
    });

    expect(screen.queryByText("firewall.example.local")).not.toBeInTheDocument();
    expect(screen.getAllByText("10.0.5.2").length).toBeGreaterThan(0);
  });

  it("shows a no-match empty state when filters exclude all assets, keeping the full stats row", async () => {
    mockFetchAssetsOnce([FIREWALL_ASSET, DOWN_SERVER_ASSET]);

    renderWithDashboardData(<NetworkTopology />);
    await screen.findByText("firewall.example.local");

    fireEvent.change(screen.getByLabelText(tr.topology.searchAriaLabel), {
      target: { value: "no-such-device" },
    });

    expect(await screen.findByText(tr.topology.noMatchFilters)).toBeInTheDocument();
    // stats row stays based on the full unfiltered asset list
    expect(screen.getByText(tr.topology.stats.devices)).toBeInTheDocument();
    const devicesStat = screen.getByText(tr.topology.stats.devices).closest("div");
    expect(within(devicesStat as HTMLElement).getByText("2")).toBeInTheDocument();
  });

  it("pre-fills the search and opens details for a device deep-linked via ?ip=", async () => {
    mockSearchParams = new URLSearchParams({ ip: "10.0.5.2" });
    mockFetchAssetsOnce([FIREWALL_ASSET, DOWN_SERVER_ASSET]);

    renderWithDashboardData(<NetworkTopology />);

    const panel = await screen.findByLabelText(tr.assetDetails.ariaLabel);
    expect(within(panel).getAllByText("10.0.5.2").length).toBeGreaterThan(0);
    expect(screen.getByLabelText(tr.topology.searchAriaLabel)).toHaveValue("10.0.5.2");
  });
});
