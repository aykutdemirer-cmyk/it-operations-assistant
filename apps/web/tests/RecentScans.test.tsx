import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RecentScans } from "@/components/RecentScans";
import { tr } from "@/lib/i18n/translations";
import { mockAssetsAndScans, renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
});

const COMPLETED_SCAN = {
  id: "11111111-1111-1111-1111-111111111111",
  cidr: "10.0.5.0/24",
  started_at: "2026-08-26T10:00:00Z",
  completed_at: "2026-08-26T10:00:02Z",
  duration_ms: 2000,
  hosts_scanned: 254,
  hosts_discovered: 3,
  open_ports: 5,
  status: "completed",
};

const RUNNING_SCAN = {
  id: "22222222-2222-2222-2222-222222222222",
  cidr: "10.0.6.0/24",
  started_at: "2026-08-26T11:00:00Z",
  completed_at: null,
  duration_ms: null,
  hosts_scanned: 0,
  hosts_discovered: 0,
  open_ports: 0,
  status: "running",
};

const FAILED_SCAN = {
  id: "33333333-3333-3333-3333-333333333333",
  cidr: "not-a-cidr",
  started_at: "2026-08-26T09:00:00Z",
  completed_at: "2026-08-26T09:00:00Z",
  duration_ms: 30,
  hosts_scanned: 0,
  hosts_discovered: 0,
  open_ports: 0,
  status: "failed",
};

function mockScans(scans: unknown[]) {
  mockAssetsAndScans([], scans);
}

describe("RecentScans", () => {
  it("shows a loading state while the request is in flight", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    renderWithDashboardData(<RecentScans />);

    expect(screen.getByText(tr.scans.loading)).toBeInTheDocument();
  });

  it("shows an empty state when there are no scans", async () => {
    mockScans([]);

    renderWithDashboardData(<RecentScans />);

    expect(await screen.findByText(tr.scans.noScans)).toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) }),
    );

    renderWithDashboardData(<RecentScans />);

    expect(await screen.findByText(tr.scans.error)).toBeInTheDocument();
  });

  it("renders scan data: cidr, started, duration, hosts discovered, open ports", async () => {
    mockScans([COMPLETED_SCAN]);

    renderWithDashboardData(<RecentScans />);

    expect(await screen.findByText("10.0.5.0/24")).toBeInTheDocument();
    expect(screen.getByText("2.0s")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("shows a completed badge", async () => {
    mockScans([COMPLETED_SCAN]);

    renderWithDashboardData(<RecentScans />);

    expect(
      await screen.findByText(tr.scans.statusLabels.completed),
    ).toBeInTheDocument();
  });

  it("shows a running badge", async () => {
    mockScans([RUNNING_SCAN]);

    renderWithDashboardData(<RecentScans />);

    expect(await screen.findByText(tr.scans.statusLabels.running)).toBeInTheDocument();
  });

  it("shows a failed badge", async () => {
    mockScans([FAILED_SCAN]);

    renderWithDashboardData(<RecentScans />);

    expect(await screen.findByText(tr.scans.statusLabels.failed)).toBeInTheDocument();
  });

  it("shows at most 5 scans by default", async () => {
    mockScans(
      Array.from({ length: 8 }, (_, i) => ({
        ...COMPLETED_SCAN,
        id: `scan-${i}`,
        cidr: `10.0.${i}.0/24`,
      })),
    );

    renderWithDashboardData(<RecentScans />);

    await waitFor(() => expect(screen.getAllByText(/^10\.0\.\d\.0\/24$/)).toHaveLength(5));
  });

  it("respects a custom limit prop", async () => {
    mockScans(
      Array.from({ length: 8 }, (_, i) => ({
        ...COMPLETED_SCAN,
        id: `scan-${i}`,
        cidr: `10.0.${i}.0/24`,
      })),
    );

    renderWithDashboardData(<RecentScans limit={8} />);

    await waitFor(() => expect(screen.getAllByText(/^10\.0\.\d\.0\/24$/)).toHaveLength(8));
  });

  it("refetches when a network-scan-completed event is dispatched", async () => {
    let currentScans: unknown[] = [COMPLETED_SCAN];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/api/scans")) {
          return Promise.resolve({ ok: true, json: async () => currentScans });
        }
        return Promise.resolve({ ok: true, json: async () => [] });
      }),
    );

    renderWithDashboardData(<RecentScans />);
    await screen.findByText("10.0.5.0/24");

    currentScans = [RUNNING_SCAN, COMPLETED_SCAN];
    act(() => {
      window.dispatchEvent(new CustomEvent("network-scan-completed"));
    });

    expect(await screen.findByText("10.0.6.0/24")).toBeInTheDocument();
  });

  it("shows hosts scanned and completed timestamp columns", async () => {
    mockScans([COMPLETED_SCAN]);

    renderWithDashboardData(<RecentScans />);

    await screen.findByText("10.0.5.0/24");
    expect(screen.getByText("254")).toBeInTheDocument();
    expect(
      screen.getByText(new Date(COMPLETED_SCAN.completed_at).toLocaleString()),
    ).toBeInTheDocument();
  });

  it("opens scan details when a row is clicked and closes on close button", async () => {
    mockScans([COMPLETED_SCAN]);

    renderWithDashboardData(<RecentScans />);
    const row = (await screen.findByText("10.0.5.0/24")).closest("tr");
    fireEvent.click(row as HTMLElement);

    const panel = screen.getByLabelText(tr.scans.details.ariaLabel);
    expect(within(panel).getByText(COMPLETED_SCAN.id)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: tr.scans.details.closeButton }));
    expect(screen.queryByLabelText(tr.scans.details.ariaLabel)).not.toBeInTheDocument();
  });
});
