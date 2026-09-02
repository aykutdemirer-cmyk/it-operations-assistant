import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GlobalSearch } from "@/components/GlobalSearch";
import { tr } from "@/lib/i18n/translations";
import { mockAssetsAndScans, renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
});

const FIREWALL_ASSET = {
  id: "11111111-1111-1111-1111-111111111111",
  ip_address: "10.0.5.1",
  hostname: "firewall.example.local",
  mac_address: "AA-BB-CC-DD-EE-FF",
  vendor: "Fortinet, Inc.",
  device_type: "firewall",
  confidence: "high",
  evidence: [],
  open_ports: [],
  status: "up",
  latency_ms: 2.1,
  last_seen: "2026-08-26T10:00:00Z",
  created_at: "2026-08-26T09:00:00Z",
  updated_at: "2026-08-26T10:00:00Z",
};

const SERVER_ASSET = {
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

describe("GlobalSearch", () => {
  it("shows no dropdown when the query is empty", async () => {
    mockAssetsAndScans([FIREWALL_ASSET, SERVER_ASSET], []);

    renderWithDashboardData(<GlobalSearch />);

    fireEvent.focus(screen.getByLabelText(tr.globalSearch.ariaLabel));

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("finds a device by hostname substring", async () => {
    mockAssetsAndScans([FIREWALL_ASSET, SERVER_ASSET], []);

    renderWithDashboardData(<GlobalSearch />);
    fireEvent.change(screen.getByLabelText(tr.globalSearch.ariaLabel), {
      target: { value: "firewall" },
    });

    expect(await screen.findByText("firewall.example.local")).toBeInTheDocument();
    expect(screen.queryByText("10.0.5.2")).not.toBeInTheDocument();
  });

  it("finds a device by ip address", async () => {
    mockAssetsAndScans([FIREWALL_ASSET, SERVER_ASSET], []);

    renderWithDashboardData(<GlobalSearch />);
    fireEvent.change(screen.getByLabelText(tr.globalSearch.ariaLabel), {
      target: { value: "10.0.5.2" },
    });

    expect(await screen.findByText("10.0.5.2")).toBeInTheDocument();
  });

  it("shows a no-match message when nothing matches", async () => {
    mockAssetsAndScans([FIREWALL_ASSET], []);

    renderWithDashboardData(<GlobalSearch />);
    fireEvent.change(screen.getByLabelText(tr.globalSearch.ariaLabel), {
      target: { value: "no-such-device" },
    });

    expect(await screen.findByText(tr.globalSearch.noMatches)).toBeInTheDocument();
  });

  it("opens the asset details panel when a result is selected and clears the search", async () => {
    mockAssetsAndScans([FIREWALL_ASSET], []);

    renderWithDashboardData(<GlobalSearch />);
    const input = screen.getByLabelText(tr.globalSearch.ariaLabel);
    fireEvent.change(input, { target: { value: "firewall" } });

    fireEvent.click(await screen.findByText("firewall.example.local"));

    expect(screen.getByLabelText(tr.assetDetails.ariaLabel)).toBeInTheDocument();
    expect((input as HTMLInputElement).value).toBe("");
  });
});
