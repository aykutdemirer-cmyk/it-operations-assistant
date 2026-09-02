import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssetInventory } from "@/components/AssetInventory";
import { tr } from "@/lib/i18n/translations";
import { mockAssetsAndScans, renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
});

const SAMPLE_ASSET = {
  id: "11111111-1111-1111-1111-111111111111",
  ip_address: "10.0.5.1",
  hostname: "firewall.example.local",
  mac_address: "AA-BB-CC-DD-EE-FF",
  vendor: "Fortinet, Inc.",
  device_type: "firewall",
  confidence: "high",
  evidence: ["vendor: Fortinet"],
  open_ports: [
    { port: 22, status: "open", latency_ms: 2.0 },
    { port: 443, status: "open", latency_ms: 2.4 },
  ],
  status: "up",
  latency_ms: 2.1,
  last_seen: "2026-08-26T10:00:00Z",
  created_at: "2026-08-26T09:00:00Z",
  updated_at: "2026-08-26T10:00:00Z",
};

const NULL_FIELD_ASSET = {
  id: "22222222-2222-2222-2222-222222222222",
  ip_address: "10.0.5.2",
  hostname: null,
  mac_address: null,
  vendor: null,
  device_type: "unknown",
  confidence: "low",
  evidence: [],
  open_ports: [],
  status: "down",
  latency_ms: null,
  last_seen: "2026-08-26T08:00:00Z",
  created_at: "2026-08-26T07:00:00Z",
  updated_at: "2026-08-26T08:00:00Z",
};

const THIRD_ASSET = {
  id: "33333333-3333-3333-3333-333333333333",
  ip_address: "10.0.5.3",
  hostname: "printer01.example.local",
  mac_address: "CC-CC-CC-CC-CC-CC",
  vendor: "HP Inc.",
  device_type: "printer",
  confidence: "medium",
  evidence: ["port: 9100"],
  open_ports: [{ port: 9100, status: "open", latency_ms: 3.0 }],
  status: "up",
  latency_ms: 5.5,
  last_seen: "2026-08-26T11:00:00Z",
  created_at: "2026-08-26T09:30:00Z",
  updated_at: "2026-08-26T11:00:00Z",
};

function mockFetchAssetsOnce(assets: unknown[]) {
  mockAssetsAndScans(assets, []);
}

describe("AssetInventory", () => {
  it("fetches and renders the asset list on mount", async () => {
    mockFetchAssetsOnce([SAMPLE_ASSET]);

    renderWithDashboardData(<AssetInventory />);

    expect(await screen.findByText("10.0.5.1")).toBeInTheDocument();
    expect(screen.getByText("firewall.example.local")).toBeInTheDocument();
  });

  it("renders multiple assets", async () => {
    mockFetchAssetsOnce([SAMPLE_ASSET, NULL_FIELD_ASSET]);

    renderWithDashboardData(<AssetInventory />);

    expect(await screen.findByText("10.0.5.1")).toBeInTheDocument();
    expect(screen.getByText("10.0.5.2")).toBeInTheDocument();
  });

  it("shows '-' for null fields", async () => {
    mockFetchAssetsOnce([NULL_FIELD_ASSET]);

    renderWithDashboardData(<AssetInventory />);

    const row = (await screen.findByText("10.0.5.2")).closest("tr");
    expect(row).not.toBeNull();
    // hostname, mac_address, vendor, open_ports, latency_ms hepsi NULL
    expect(within(row as HTMLElement).getAllByText("-")).toHaveLength(5);
  });

  it("renders open ports as individual chips", async () => {
    mockFetchAssetsOnce([SAMPLE_ASSET]);

    renderWithDashboardData(<AssetInventory />);

    const row = (await screen.findByText("10.0.5.1")).closest("tr");
    expect(within(row as HTMLElement).getByText("22")).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText("443")).toBeInTheDocument();
  });

  it("shows a loading state while the request is in flight", async () => {
    let resolveFetch: (value: unknown) => void = () => {};
    const pending = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending));

    renderWithDashboardData(<AssetInventory />);

    expect(screen.getByText(tr.common.loading)).toBeInTheDocument();

    resolveFetch({ ok: true, json: async () => [] });

    await waitFor(() =>
      expect(screen.queryByText(tr.common.loading)).not.toBeInTheDocument(),
    );
  });

  it("shows an empty state when there are no assets", async () => {
    mockFetchAssetsOnce([]);

    renderWithDashboardData(<AssetInventory />);

    expect(await screen.findByText(tr.assets.emptyText)).toBeInTheDocument();
    expect(screen.getByText(tr.assets.emptyHint)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: tr.assets.goToDiscovery }),
    ).toHaveAttribute("href", "/discovery");
  });

  it("shows an error state when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({ detail: { database: "unreachable" } }),
      }),
    );

    renderWithDashboardData(<AssetInventory />);

    expect(await screen.findByText("unreachable")).toBeInTheDocument();
  });

  it("refetches assets when the Refresh button is clicked", async () => {
    let currentAssets: unknown[] = [SAMPLE_ASSET];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/api/assets")) {
          return Promise.resolve({ ok: true, json: async () => currentAssets });
        }
        return Promise.resolve({ ok: true, json: async () => [] });
      }),
    );

    renderWithDashboardData(<AssetInventory />);
    await screen.findByText("10.0.5.1");

    currentAssets = [SAMPLE_ASSET, NULL_FIELD_ASSET];
    fireEvent.click(screen.getByRole("button", { name: tr.common.refresh }));

    expect(await screen.findByText("10.0.5.2")).toBeInTheDocument();
  });

  it("filters assets by search text", async () => {
    mockFetchAssetsOnce([SAMPLE_ASSET, NULL_FIELD_ASSET, THIRD_ASSET]);

    renderWithDashboardData(<AssetInventory />);
    await screen.findByText("10.0.5.1");

    fireEvent.change(screen.getByLabelText(tr.assets.searchAriaLabel), {
      target: { value: "printer01" },
    });

    expect(screen.getByText("10.0.5.3")).toBeInTheDocument();
    expect(screen.queryByText("10.0.5.1")).not.toBeInTheDocument();
    expect(screen.queryByText("10.0.5.2")).not.toBeInTheDocument();
  });

  it("filters assets by status", async () => {
    mockFetchAssetsOnce([SAMPLE_ASSET, NULL_FIELD_ASSET, THIRD_ASSET]);

    renderWithDashboardData(<AssetInventory />);
    await screen.findByText("10.0.5.1");

    fireEvent.change(screen.getByLabelText(tr.assets.filterByStatus), {
      target: { value: "down" },
    });

    expect(screen.getByText("10.0.5.2")).toBeInTheDocument();
    expect(screen.queryByText("10.0.5.1")).not.toBeInTheDocument();
    expect(screen.queryByText("10.0.5.3")).not.toBeInTheDocument();
  });

  it("filters assets by device type", async () => {
    mockFetchAssetsOnce([SAMPLE_ASSET, NULL_FIELD_ASSET, THIRD_ASSET]);

    renderWithDashboardData(<AssetInventory />);
    await screen.findByText("10.0.5.1");

    fireEvent.change(screen.getByLabelText(tr.assets.filterByDeviceType), {
      target: { value: "printer" },
    });

    expect(screen.getByText("10.0.5.3")).toBeInTheDocument();
    expect(screen.queryByText("10.0.5.1")).not.toBeInTheDocument();
    expect(screen.queryByText("10.0.5.2")).not.toBeInTheDocument();
  });

  it("filters assets by vendor", async () => {
    mockFetchAssetsOnce([SAMPLE_ASSET, NULL_FIELD_ASSET, THIRD_ASSET]);

    renderWithDashboardData(<AssetInventory />);
    await screen.findByText("10.0.5.1");

    fireEvent.change(screen.getByLabelText(tr.assets.filterByVendor), {
      target: { value: "HP Inc." },
    });

    expect(screen.getByText("10.0.5.3")).toBeInTheDocument();
    expect(screen.queryByText("10.0.5.1")).not.toBeInTheDocument();
  });

  it("filters assets by confidence", async () => {
    mockFetchAssetsOnce([SAMPLE_ASSET, NULL_FIELD_ASSET, THIRD_ASSET]);

    renderWithDashboardData(<AssetInventory />);
    await screen.findByText("10.0.5.1");

    fireEvent.change(screen.getByLabelText(tr.assets.filterByConfidence), {
      target: { value: "high" },
    });

    expect(screen.getByText("10.0.5.1")).toBeInTheDocument();
    expect(screen.queryByText("10.0.5.2")).not.toBeInTheDocument();
    expect(screen.queryByText("10.0.5.3")).not.toBeInTheDocument();
  });

  it("shows a filtered empty state when no assets match the filters", async () => {
    mockFetchAssetsOnce([SAMPLE_ASSET, NULL_FIELD_ASSET, THIRD_ASSET]);

    renderWithDashboardData(<AssetInventory />);
    await screen.findByText("10.0.5.1");

    fireEvent.change(screen.getByLabelText(tr.assets.searchAriaLabel), {
      target: { value: "no-such-host" },
    });

    expect(await screen.findByText(tr.assets.noMatchFilters)).toBeInTheDocument();
  });

  it("shows the SNMP status column — not configured by default", async () => {
    mockFetchAssetsOnce([SAMPLE_ASSET]);

    renderWithDashboardData(<AssetInventory />);

    const row = (await screen.findByText("10.0.5.1")).closest("tr") as HTMLElement;
    expect(await within(row).findByText(new RegExp(tr.assets.snmpNotConfigured))).toBeInTheDocument();
  });

  it("shows the SNMP status column with the profile name when configured", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/snmp-profile")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              configured: true,
              target_host_matches_asset: true,
              profile: { name: "Core Switch SNMP" },
            }),
          });
        }
        if (url.includes("/api/assets")) {
          return Promise.resolve({ ok: true, json: async () => [SAMPLE_ASSET] });
        }
        return Promise.resolve({ ok: true, json: async () => [] });
      }),
    );

    renderWithDashboardData(<AssetInventory />);

    const row = (await screen.findByText("10.0.5.1")).closest("tr") as HTMLElement;
    expect(
      await within(row).findByText(new RegExp(`${tr.assets.snmpConfigured}.*Core Switch SNMP`)),
    ).toBeInTheDocument();
  });

  it("opens the asset details panel when a row is clicked", async () => {
    mockFetchAssetsOnce([SAMPLE_ASSET]);

    renderWithDashboardData(<AssetInventory />);
    const row = (await screen.findByText("10.0.5.1")).closest("tr");
    fireEvent.click(row as HTMLElement);

    const panel = screen.getByLabelText(tr.assetDetails.ariaLabel);
    expect(
      within(panel).getAllByText("firewall.example.local").length,
    ).toBeGreaterThan(0);

    fireEvent.click(
      within(panel).getByRole("tab", { name: tr.assetDetails.tabs.network }),
    );
    expect(within(panel).getByText("AA-BB-CC-DD-EE-FF")).toBeInTheDocument();

    fireEvent.click(
      within(panel).getByRole("tab", { name: tr.assetDetails.tabs.discovery }),
    );
    expect(within(panel).getByText("vendor: Fortinet")).toBeInTheDocument();
  });

  it("closes the asset details panel when the close button is clicked", async () => {
    mockFetchAssetsOnce([SAMPLE_ASSET]);

    renderWithDashboardData(<AssetInventory />);
    const row = (await screen.findByText("10.0.5.1")).closest("tr");
    fireEvent.click(row as HTMLElement);

    expect(screen.getByLabelText(tr.assetDetails.ariaLabel)).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: tr.assetDetails.closeButton }),
    );

    expect(screen.queryByLabelText(tr.assetDetails.ariaLabel)).not.toBeInTheDocument();
  });
});
