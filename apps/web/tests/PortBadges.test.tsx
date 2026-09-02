import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PortBadges } from "@/components/PortBadges";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import type { PortResult } from "@/lib/api";

function ports(...nums: number[]): PortResult[] {
  return nums.map((port) => ({ port, status: "open" as const, latency_ms: null }));
}

function renderBadges(list: PortResult[]) {
  return render(
    <LocaleProvider>
      <PortBadges ports={list} />
    </LocaleProvider>
  );
}

describe("PortBadges", () => {
  it("shows '-' when there are no ports", () => {
    renderBadges([]);
    expect(screen.getByText("-")).toBeInTheDocument();
  });

  it("shows each port as its own chip when 3 or fewer", () => {
    renderBadges(ports(80, 443, 22));
    expect(screen.getByText("80")).toBeInTheDocument();
    expect(screen.getByText("443")).toBeInTheDocument();
    expect(screen.getByText("22")).toBeInTheDocument();
    expect(screen.queryByText(/daha/)).not.toBeInTheDocument();
  });

  it("shows only 3 ports plus a '+X daha' badge when there are more", () => {
    renderBadges(ports(80, 443, 22, 3389, 8080));
    expect(screen.getByText("80")).toBeInTheDocument();
    expect(screen.getByText("443")).toBeInTheDocument();
    expect(screen.getByText("22")).toBeInTheDocument();
    expect(screen.queryByText("3389")).not.toBeInTheDocument();
    expect(screen.getByText(/\+2 daha/)).toBeInTheDocument();
  });

  it("opens a popover listing all ports grouped by risk when clicking '+X daha'", () => {
    renderBadges(ports(80, 443, 22, 3389, 445));
    fireEvent.click(screen.getByText(/\+2 daha/));

    // 3389 ve 445 HIGH risk portlarıdır (bkz. lib/portRisk.ts) — popover'da görünmeli.
    expect(screen.getByText("3389, 445")).toBeInTheDocument();
  });
});
