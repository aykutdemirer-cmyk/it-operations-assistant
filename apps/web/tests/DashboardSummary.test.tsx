import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DashboardSummary } from "@/components/DashboardSummary";
import { tr } from "@/lib/i18n/translations";
import { renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
});

const ASSETS = [
  {
    id: "1",
    status: "up",
    device_type: "firewall",
    open_ports: [{ port: 443, status: "open", latency_ms: 1 }],
    last_seen: "2026-08-26T08:00:00Z",
  },
  {
    id: "2",
    status: "up",
    device_type: "network_device",
    open_ports: [
      { port: 22, status: "open", latency_ms: 1 },
      { port: 80, status: "open", latency_ms: 1 },
    ],
    last_seen: "2026-08-26T10:00:00Z",
  },
  {
    id: "3",
    status: "down",
    device_type: "server",
    open_ports: [],
    last_seen: "2026-08-26T06:00:00Z",
  },
  {
    id: "4",
    status: "up",
    device_type: "unknown",
    open_ports: [{ port: 3389, status: "open", latency_ms: 1 }],
    last_seen: "2026-08-26T09:00:00Z",
  },
];

function cardValue(label: string): string {
  const labelEl = screen.getByText(label);
  // label -> .cardTop -> .card
  const card = labelEl.parentElement?.parentElement as HTMLElement;
  const valueEl = card.querySelector('[class*="value"]');
  return valueEl?.textContent ?? "";
}

function mockAssets() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ASSETS,
    }),
  );
}

describe("DashboardSummary", () => {
  it("shows exactly 4 consolidated KPI cards", async () => {
    mockAssets();
    renderWithDashboardData(<DashboardSummary />);

    const s = tr.dashboard.summary;
    await waitFor(() => expect(cardValue(s.totalAssets)).toBe("4"));
    expect(screen.getByText(s.totalAssets)).toBeInTheDocument();
    expect(screen.getByText(s.highRiskPortsCard)).toBeInTheDocument();
    expect(screen.getByText(s.unknown)).toBeInTheDocument();
    expect(screen.getByText(s.healthScoreCard)).toBeInTheDocument();
    // Eski, tek tek dağınık kartlar artık YOK.
    expect(screen.queryByText(s.firewalls)).not.toBeInTheDocument();
    expect(screen.queryByText(s.networkDevices)).not.toBeInTheDocument();
    expect(screen.queryByText(s.servers)).not.toBeInTheDocument();
  });

  it("shows online/offline mini badges on the Total Assets card", async () => {
    mockAssets();
    renderWithDashboardData(<DashboardSummary />);

    await waitFor(() => expect(cardValue(tr.dashboard.summary.totalAssets)).toBe("4"));
    expect(screen.getByText(/3.*Çevrimiçi/)).toBeInTheDocument();
    expect(screen.getByText(/1.*Çevrimdışı/)).toBeInTheDocument();
  });

  it("counts devices with high-risk open ports (e.g. RDP/3389), not just total ports", async () => {
    mockAssets();
    renderWithDashboardData(<DashboardSummary />);

    // Yalnızca asset id=4 3389 (HIGH risk) taşıyor.
    await waitFor(() => expect(cardValue(tr.dashboard.summary.highRiskPortsCard)).toBe("1"));
  });

  it("computes unknown device count", async () => {
    mockAssets();
    renderWithDashboardData(<DashboardSummary />);

    await waitFor(() => expect(cardValue(tr.dashboard.summary.unknown)).toBe("1"));
  });

  it("shows an infrastructure health score based on online ratio", async () => {
    mockAssets();
    renderWithDashboardData(<DashboardSummary />);

    // 3/4 çevrimiçi = %75.
    await waitFor(() => expect(cardValue(tr.dashboard.summary.healthScoreCard)).toBe("75%"));
  });

  it("shows the most recent last-seen timestamp as passive corner text, not a KPI card", async () => {
    mockAssets();
    renderWithDashboardData(<DashboardSummary />);

    await waitFor(() =>
      expect(
        screen.getByText(
          `${tr.dashboard.summary.lastSeen}: ${new Date("2026-08-26T10:00:00Z").toLocaleString()}`,
        ),
      ).toBeInTheDocument(),
    );
    // Bu bilgi artık bir KPI kartı DEĞİL — "value" sınıfı taşıyan bir elemanın içinde olmamalı.
    expect(screen.queryByText(tr.dashboard.summary.lastSeen)).not.toBeInTheDocument();
  });

  it("shows a placeholder while loading", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    renderWithDashboardData(<DashboardSummary />);

    expect(cardValue(tr.dashboard.summary.totalAssets)).toBe("–");
  });
});
