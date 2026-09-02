import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RecentActivity } from "@/components/RecentActivity";
import { tr } from "@/lib/i18n/translations";
import { mockAssetsAndScans, renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
});

const now = new Date();
const recentIso = now.toISOString();
const olderIso = new Date(now.getTime() - 60 * 60 * 1000).toISOString();
const a = tr.dashboard.recentActivity;

describe("RecentActivity", () => {
  it("shows a loading state", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    renderWithDashboardData(<RecentActivity />);

    expect(screen.getByText(tr.common.loading)).toBeInTheDocument();
  });

  it("shows an empty state without fabricating activity when there is no data", async () => {
    mockAssetsAndScans([], []);

    renderWithDashboardData(<RecentActivity />);

    expect(await screen.findByText(a.noActivity)).toBeInTheDocument();
  });

  it("shows an error state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) }),
    );

    renderWithDashboardData(<RecentActivity />);

    expect(await screen.findByText(tr.common.unableToLoad)).toBeInTheDocument();
  });

  it("shows 'Asset discovered' for a newly-created asset (created_at === updated_at)", async () => {
    mockAssetsAndScans(
      [
        {
          id: "1",
          ip_address: "10.0.5.1",
          hostname: "new-host.local",
          created_at: recentIso,
          updated_at: recentIso,
        },
      ],
      [],
    );

    renderWithDashboardData(<RecentActivity />);

    expect(
      await screen.findByText(`${a.assetDiscovered} · new-host.local`),
    ).toBeInTheDocument();
  });

  it("shows 'Asset updated' when updated_at differs from created_at", async () => {
    mockAssetsAndScans(
      [
        {
          id: "1",
          ip_address: "10.0.5.2",
          hostname: "existing-host.local",
          created_at: olderIso,
          updated_at: recentIso,
        },
      ],
      [],
    );

    renderWithDashboardData(<RecentActivity />);

    expect(
      await screen.findByText(`${a.assetUpdated} · existing-host.local`),
    ).toBeInTheDocument();
  });

  it("shows real scan completion and failure events", async () => {
    mockAssetsAndScans(
      [],
      [
        {
          id: "s1",
          cidr: "10.0.5.0/24",
          status: "completed",
          completed_at: recentIso,
        },
        {
          id: "s2",
          cidr: "not-a-cidr",
          status: "failed",
          completed_at: olderIso,
        },
      ],
    );

    renderWithDashboardData(<RecentActivity />);

    expect(
      await screen.findByText(`${a.scanCompleted} · 10.0.5.0/24`),
    ).toBeInTheDocument();
    expect(screen.getByText(`${a.scanFailed} · not-a-cidr`)).toBeInTheDocument();
  });

  it("orders events by most recent first", async () => {
    mockAssetsAndScans(
      [
        {
          id: "1",
          ip_address: "10.0.5.1",
          hostname: "older-asset",
          created_at: olderIso,
          updated_at: olderIso,
        },
      ],
      [
        {
          id: "s1",
          cidr: "10.0.5.0/24",
          status: "completed",
          completed_at: recentIso,
        },
      ],
    );

    renderWithDashboardData(<RecentActivity />);

    await waitFor(() => expect(screen.getByRole("list").children).toHaveLength(2));
    const [first, second] = screen.getByRole("list").children;
    expect(first.textContent).toContain(a.scanCompleted);
    expect(second.textContent).toContain("older-asset");
  });
});
