import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ScanDetails } from "@/components/ScanDetails";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import type { Scan } from "@/lib/api";

const SCAN: Scan = {
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

function renderScanDetails(scan: Scan, onClose: () => void) {
  return render(
    <LocaleProvider>
      <ScanDetails scan={scan} onClose={onClose} />
    </LocaleProvider>,
  );
}

describe("ScanDetails", () => {
  it("renders all scan fields with the real scan id", () => {
    renderScanDetails(SCAN, vi.fn());

    expect(screen.getByText(SCAN.id)).toBeInTheDocument();
    expect(screen.getByText(tr.scans.statusLabels.completed)).toBeInTheDocument();
    expect(screen.getByText("254")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("2.0s")).toBeInTheDocument();
  });

  it("shows '-' for a running scan with no completed_at/duration", () => {
    renderScanDetails(
      { ...SCAN, status: "running", completed_at: null, duration_ms: null },
      vi.fn(),
    );

    expect(screen.getByText(tr.scans.statusLabels.running)).toBeInTheDocument();
    const dashes = screen.getAllByText("-");
    expect(dashes.length).toBe(2); // completed, duration
  });

  it("calls onClose when the close button is clicked", () => {
    const onClose = vi.fn();
    renderScanDetails(SCAN, onClose);

    fireEvent.click(screen.getByRole("button", { name: tr.scans.details.closeButton }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when Escape is pressed", () => {
    const onClose = vi.fn();
    renderScanDetails(SCAN, onClose);

    fireEvent.keyDown(window, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
