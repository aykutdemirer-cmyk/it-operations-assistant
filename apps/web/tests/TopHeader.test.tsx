import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TopHeader } from "@/components/TopHeader";
import { tr } from "@/lib/i18n/translations";
import { mockAssetsAndScans, renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("TopHeader", () => {
  it("shows the app subtitle in Turkish by default", () => {
    mockAssetsAndScans([], []);

    renderWithDashboardData(<TopHeader />);

    expect(screen.getByText(tr.common.appSubtitle)).toBeInTheDocument();
  });

  it("switches the subtitle to English when EN is clicked", async () => {
    mockAssetsAndScans([], []);

    renderWithDashboardData(<TopHeader />);

    fireEvent.click(screen.getByRole("button", { name: "EN" }));

    await waitFor(() =>
      expect(screen.getByText("Network Infrastructure")).toBeInTheDocument(),
    );
  });

  it("switches back to Turkish when TR is clicked", async () => {
    mockAssetsAndScans([], []);

    renderWithDashboardData(<TopHeader />);

    fireEvent.click(screen.getByRole("button", { name: "EN" }));
    await waitFor(() =>
      expect(screen.getByText("Network Infrastructure")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "TR" }));
    await waitFor(() =>
      expect(screen.getByText(tr.common.appSubtitle)).toBeInTheDocument(),
    );
  });
});
