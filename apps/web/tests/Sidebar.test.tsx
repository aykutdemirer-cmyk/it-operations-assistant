import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { usePathname } = vi.hoisted(() => ({ usePathname: vi.fn(() => "/") }));
vi.mock("next/navigation", () => ({ usePathname }));

import { Sidebar } from "@/components/Sidebar";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { ALL_PERMISSIONS, type Permission } from "@/lib/auth/permissions";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

// Faz 47 — Sidebar artık `currentUser.permissions`'a göre dinamik
// render ediyor; bu yüzden "her öğe görünür" senaryosunu test etmek
// için ÖNCE bir kullanıcının TÜM izinlere sahip olduğunu mock'lamak
// gerekiyor (giriş yapılmamışken Sidebar KASITLI olarak boş).
function mockLoggedInUser(permissions: Permission[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.includes("/api/auth/me")) {
        return Promise.resolve({ ok: true, json: async () => mockCurrentUser(permissions) });
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    }),
  );
  setLoggedInToken();
}

async function renderSidebar(permissions: Permission[] = ALL_PERMISSIONS) {
  mockLoggedInUser(permissions);
  const result = render(
    <LocaleProvider>
      <AuthProvider>
        <Sidebar />
      </AuthProvider>
    </LocaleProvider>,
  );
  // Kullanıcı state'i bir microtask'a ertelendi (bkz. `AuthProvider.tsx`
  // — react-hooks/set-state-in-effect) — menü öğeleri belirmeden önce
  // bekliyoruz.
  if (permissions.length > 0) {
    await screen.findAllByRole("link");
  } else {
    await waitFor(() => expect(screen.queryAllByRole("link")).toHaveLength(0));
  }
  return result;
}

afterEach(() => {
  usePathname.mockReturnValue("/");
  window.localStorage.clear();
});

describe("Sidebar", () => {
  it("renders every menu item as a real route, grouped correctly (full permissions)", async () => {
    await renderSidebar();

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
    expect(
      screen.getByRole("link", { name: new RegExp(tr.nav.pamUsers) }),
    ).toHaveAttribute("href", "/pam/users");
  });

  it("shows every group label when the user has full permissions", async () => {
    await renderSidebar();

    expect(screen.getByText(tr.nav.groupOverview)).toBeInTheDocument();
    expect(screen.getByText(tr.nav.groupDiscovery)).toBeInTheDocument();
    expect(screen.getByText(tr.nav.groupOperations)).toBeInTheDocument();
    expect(screen.getByText(tr.nav.groupSystem)).toBeInTheDocument();
    expect(screen.getByText(tr.nav.groupPam)).toBeInTheDocument();
  });

  it("marks the current page's nav link as active", async () => {
    await renderSidebar();

    expect(screen.getByRole("link", { name: /Dashboard/ }).className).toMatch(
      /navLinkActive/,
    );
  });

  it("marks the Agents nav link active on an agent detail sub-route (Faz 30)", async () => {
    usePathname.mockReturnValue("/agents/11111111-1111-1111-1111-111111111111");
    await renderSidebar();

    expect(screen.getByRole("link", { name: new RegExp(tr.nav.agents) }).className).toMatch(
      /navLinkActive/,
    );
  });

  it("toggles the mobile menu open and closed via the hamburger button", async () => {
    await renderSidebar();

    const toggle = screen.getByRole("button", { name: tr.nav.openMenu });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);

    expect(screen.getByRole("button", { name: tr.nav.closeMenu })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("closes the mobile menu when a nav link is clicked", async () => {
    await renderSidebar();

    fireEvent.click(screen.getByRole("button", { name: tr.nav.openMenu }));
    fireEvent.click(screen.getByRole("link", { name: new RegExp(tr.nav.alerts) }));

    expect(screen.getByRole("button", { name: tr.nav.openMenu })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  // Faz 47 — kullanıcının açık örneği: yalnızca `PAM_ACCESS` izni olan
  // bir kullanıcı Dashboard dahil hiçbir genel menüyü görmesin, yalnızca
  // "Erişilebilir Sunucularım"ı görsün.
  it("shows only the my-access link for a user with just PAM_ACCESS", async () => {
    await renderSidebar(["PAM_ACCESS"]);

    expect(screen.getByRole("link", { name: new RegExp(tr.pam.myAccessTitle) })).toHaveAttribute(
      "href",
      "/my-access",
    );
    expect(screen.queryByRole("link", { name: /Dashboard/ })).not.toBeInTheDocument();
    expect(screen.queryByText(tr.nav.groupOverview)).not.toBeInTheDocument();
    expect(screen.queryByText(tr.nav.groupPam)).not.toBeInTheDocument();
  });

  it("shows no menu items when the user has no permissions at all", async () => {
    await renderSidebar([]);

    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });
});
