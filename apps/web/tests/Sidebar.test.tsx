import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { usePathname } = vi.hoisted(() => ({ usePathname: vi.fn(() => "/") }));
vi.mock("next/navigation", () => ({ usePathname }));

import { Sidebar } from "@/components/Sidebar";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";

function renderSidebar() {
  return render(
    <LocaleProvider>
      <Sidebar />
    </LocaleProvider>,
  );
}

afterEach(() => {
  usePathname.mockReturnValue("/");
});

describe("Sidebar", () => {
  it("renders every menu item as a real route, grouped correctly", () => {
    renderSidebar();

    expect(screen.getByRole("link", { name: /Dashboard/ })).toHaveAttribute("href", "/");
    expect(
      screen.getByRole("link", { name: new RegExp(tr.nav.discovery) }),
    ).toHaveAttribute("href", "/discovery");
    expect(
      screen.getByRole("link", { name: new RegExp(tr.nav.assets) }),
    ).toHaveAttribute("href", "/assets");
    expect(
      screen.getByRole("link", { name: new RegExp(tr.nav.topology) }),
    ).toHaveAttribute("href", "/topology");
    expect(
      screen.getByRole("link", { name: new RegExp(tr.nav.scans) }),
    ).toHaveAttribute("href", "/scans");
    expect(
      screen.getByRole("link", { name: new RegExp(tr.nav.alerts) }),
    ).toHaveAttribute("href", "/alerts");
    expect(
      screen.getByRole("link", { name: new RegExp(tr.nav.monitoring) }),
    ).toHaveAttribute("href", "/monitoring");
    expect(
      screen.getByRole("link", { name: new RegExp(tr.nav.agents) }),
    ).toHaveAttribute("href", "/agents");
    expect(
      screen.getByRole("link", { name: new RegExp(tr.nav.settings) }),
    ).toHaveAttribute("href", "/settings");
  });

  it("shows the four group labels", () => {
    renderSidebar();

    expect(screen.getByText(tr.nav.groupOverview)).toBeInTheDocument();
    expect(screen.getByText(tr.nav.groupDiscovery)).toBeInTheDocument();
    expect(screen.getByText(tr.nav.groupOperations)).toBeInTheDocument();
    expect(screen.getByText(tr.nav.groupSystem)).toBeInTheDocument();
  });

  it("marks the current page's nav link as active", () => {
    renderSidebar();

    expect(screen.getByRole("link", { name: /Dashboard/ }).className).toMatch(
      /navLinkActive/,
    );
  });

  it("marks the Agents nav link active on an agent detail sub-route (Faz 30)", () => {
    usePathname.mockReturnValue("/agents/11111111-1111-1111-1111-111111111111");
    renderSidebar();

    expect(screen.getByRole("link", { name: new RegExp(tr.nav.agents) }).className).toMatch(
      /navLinkActive/,
    );
  });

  it("toggles the mobile menu open and closed via the hamburger button", () => {
    renderSidebar();

    const toggle = screen.getByRole("button", { name: tr.nav.openMenu });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);

    expect(screen.getByRole("button", { name: tr.nav.closeMenu })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("closes the mobile menu when a nav link is clicked", () => {
    renderSidebar();

    fireEvent.click(screen.getByRole("button", { name: tr.nav.openMenu }));
    fireEvent.click(screen.getByRole("link", { name: new RegExp(tr.nav.alerts) }));

    expect(screen.getByRole("button", { name: tr.nav.openMenu })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });
});
