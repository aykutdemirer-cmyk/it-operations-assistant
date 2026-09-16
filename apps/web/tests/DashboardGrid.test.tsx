import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardGrid } from "@/components/dashboard/DashboardGrid";
import { tr } from "@/lib/i18n/translations";
import { mockAssetsAndScans, renderWithProviders } from "./testUtils";

const g = tr.dashboard.grid;

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("DashboardGrid", () => {
  it("renders the default Overview view with its widgets", async () => {
    mockAssetsAndScans([], []);
    renderWithProviders(<DashboardGrid />);

    // Overview görünümü `dashboard-summary` widget'ını içerir.
    expect(await screen.findByLabelText(tr.common.dashboardSummaryAriaLabel)).toBeInTheDocument();
    expect(screen.getByLabelText(g.viewLabel)).toHaveValue("overview");
  });

  it("persists the selected view to localStorage", async () => {
    mockAssetsAndScans([], []);
    renderWithProviders(<DashboardGrid />);
    await screen.findByLabelText(g.viewLabel);

    fireEvent.change(screen.getByLabelText(g.viewLabel), { target: { value: "network" } });

    await waitFor(() => expect(window.localStorage.getItem("itops-dashboard-view")).toBe("network"));
  });

  it("hides the edit toolbar (Add/Save/Reset) until 'Edit' is clicked", async () => {
    mockAssetsAndScans([], []);
    renderWithProviders(<DashboardGrid />);
    await screen.findByLabelText(g.viewLabel);

    expect(screen.queryByRole("button", { name: `+ ${g.addWidget}` })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: `🔄 ${g.resetLayout}` })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: g.editLayout })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: g.editLayout }));

    expect(screen.getByRole("button", { name: `+ ${g.addWidget}` })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: `🔄 ${g.resetLayout}` })).toBeInTheDocument();
  });

  it("adds a widget to the empty Custom view via the Add Widget modal", async () => {
    mockAssetsAndScans([], []);
    renderWithProviders(<DashboardGrid />);
    await screen.findByLabelText(g.viewLabel);

    fireEvent.change(screen.getByLabelText(g.viewLabel), { target: { value: "custom" } });
    await screen.findByText(g.emptyCustom);

    fireEvent.click(screen.getByRole("button", { name: g.editLayout }));
    fireEvent.click(screen.getByRole("button", { name: `+ ${g.addWidget}` }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getAllByRole("button", { name: `+ ${g.addWidget}` })[0]);
    fireEvent.click(within(dialog).getByRole("button", { name: tr.common.close }));

    await waitFor(() => expect(screen.queryByText(g.emptyCustom)).not.toBeInTheDocument());
  });

  it("reset restores the default layout and clears the stored one", async () => {
    // Custom görünüm için önceden kaydedilmiş (dolu) bir düzen.
    window.localStorage.setItem("itops-dashboard-view", "custom");
    window.localStorage.setItem(
      "itops-dashboard-layout-custom",
      JSON.stringify({ widgets: ["recent-scans"], layout: [{ i: "recent-scans", x: 0, y: 0, w: 6, h: 7 }] }),
    );
    mockAssetsAndScans([], []);
    renderWithProviders(<DashboardGrid />);
    await screen.findByLabelText(g.viewLabel);

    fireEvent.click(screen.getByRole("button", { name: g.editLayout }));
    fireEvent.click(screen.getByRole("button", { name: `🔄 ${g.resetLayout}` }));

    await waitFor(() => expect(screen.getByText(g.emptyCustom)).toBeInTheDocument());
    expect(window.localStorage.getItem("itops-dashboard-layout-custom")).toBeNull();
  });

  it("closes the edit toolbar after saving the layout", async () => {
    window.localStorage.setItem("itops-dashboard-view", "custom");
    window.localStorage.setItem(
      "itops-dashboard-layout-custom",
      JSON.stringify({ widgets: ["recent-scans"], layout: [{ i: "recent-scans", x: 0, y: 0, w: 6, h: 7 }] }),
    );
    mockAssetsAndScans([], []);
    renderWithProviders(<DashboardGrid />);
    await screen.findByLabelText(g.viewLabel);

    fireEvent.click(screen.getByRole("button", { name: g.editLayout }));
    fireEvent.click(screen.getByRole("button", { name: g.remove })); // "dirty" bayrağını tetikler
    fireEvent.click(screen.getByRole("button", { name: `💾 ${g.saveLayout}` }));

    await waitFor(() => expect(screen.getByRole("button", { name: g.editLayout })).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: `+ ${g.addWidget}` })).not.toBeInTheDocument();
  });
});
