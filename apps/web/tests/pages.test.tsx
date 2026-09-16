/**
 * Her sayfanın gerçek route/dosyasının (app/**\/page.tsx) hatasız
 * render olduğunu ve o sayfaya özgü gerçek bir başlık/metin
 * gösterdiğini doğrulayan smoke testleri (bkz. Faz — "PAGE B/E").
 * Ayrıntılı davranış (filtreler, etkileşimler) ilgili component'in
 * kendi test dosyasında zaten kapsanıyor — burada yalnızca "doğru
 * component doğru route'a bağlandı mı" doğrulanır.
 *
 * Faz 47 — her sayfa artık `RequirePermission` ile sarmalı; bu yüzden
 * her render'dan önce `localStorage`'a sahte bir token yazılıp
 * `GET /api/auth/me`'nin TÜM izinlere sahip bir kullanıcı döndüğü
 * mock'lanıyor (route guard'ın KENDİSİ ayrı, kısıtlı-izin senaryolarıyla
 * `Sidebar.test.tsx`/`RequirePermission.test.tsx`'te test ediliyor).
 */
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

import Dashboard from "@/app/page";
import DiscoveryPage from "@/app/discovery/page";
import AssetsPage from "@/app/assets/page";
import TopologyPage from "@/app/topology/page";
import ScansPage from "@/app/scans/page";
import AlertsPage from "@/app/alerts/page";
import MonitoringPage from "@/app/monitoring/page";
import TicketsPage from "@/app/tickets/page";
import SettingsPage from "@/app/settings/page";
import { DashboardDataProvider } from "@/lib/DashboardDataProvider";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { ALL_PERMISSIONS } from "@/lib/auth/permissions";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { ThemeProvider } from "@/lib/theme/ThemeProvider";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

function mockAssetsAndScans() {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.includes("/api/auth/me")) {
        return Promise.resolve({ ok: true, json: async () => mockCurrentUser(ALL_PERMISSIONS) });
      }
      if (url.includes("/api/health/snmp")) {
        return Promise.resolve({ ok: true, json: async () => ({ snmp: "not_configured" }) });
      }
      if (url.includes("/api/health/db")) {
        return Promise.resolve({ ok: true, json: async () => ({ database: "ok" }) });
      }
      if (url.includes("/api/health")) {
        return Promise.resolve({ ok: true, json: async () => ({ status: "ok" }) });
      }
      if (url.includes("/api/assets")) {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      if (url.includes("/api/scans")) {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      if (url.includes("/api/monitoring")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            started_at: "2026-08-26T00:00:00Z",
            completed_at: "2026-08-26T00:00:00Z",
            duration_ms: 0,
            total: 0,
            polled: 0,
            not_configured: 0,
            results: [],
          }),
        });
      }
      if (url.includes("/api/agents")) {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      if (url.includes("/api/snmp/profiles")) {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      if (url.includes("/api/tickets/categories") || url.includes("/api/tickets/departments")) {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      if (url.includes("/api/tickets")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            tickets: [],
            total: 0,
            stats: { open_tickets: 0, assigned_to_me: 0, critical_or_overdue: 0, resolved_this_month: 0 },
          }),
        });
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    }),
  );
}

function renderPage(ui: React.ReactElement) {
  mockAssetsAndScans();
  setLoggedInToken();
  return render(
    <LocaleProvider>
      <ThemeProvider>
        <AuthProvider>
          <DashboardDataProvider>{ui}</DashboardDataProvider>
        </AuthProvider>
      </ThemeProvider>
    </LocaleProvider>,
  );
}

describe("Pages", () => {
  it("renders the Dashboard page with its summary region", async () => {
    renderPage(<Dashboard />);
    expect(await screen.findByLabelText(tr.common.dashboardSummaryAriaLabel)).toBeInTheDocument();
  });

  it("renders the Discovery page", async () => {
    renderPage(<DiscoveryPage />);
    expect(await screen.findByText(tr.discovery.title)).toBeInTheDocument();
  });

  it("renders the Assets page", async () => {
    renderPage(<AssetsPage />);
    expect(await screen.findByText(tr.assets.title)).toBeInTheDocument();
  });

  it("renders the Topology page", async () => {
    renderPage(<TopologyPage />);
    expect(await screen.findByText(tr.topology.title)).toBeInTheDocument();
  });

  it("renders the Scans page", async () => {
    renderPage(<ScansPage />);
    expect(await screen.findByText(tr.scans.title)).toBeInTheDocument();
  });

  it("renders the Alerts page", async () => {
    renderPage(<AlertsPage />);
    expect(await screen.findByText(tr.alerts.title)).toBeInTheDocument();
  });

  it("renders the Monitoring page", async () => {
    renderPage(<MonitoringPage />);
    expect(await screen.findByText(tr.monitoring.title)).toBeInTheDocument();
  });

  it("renders the Settings page", async () => {
    renderPage(<SettingsPage />);
    expect(await screen.findByText(tr.settings.title)).toBeInTheDocument();
  });

  it("renders the Tickets page", async () => {
    renderPage(<TicketsPage />);
    expect(await screen.findByText(tr.tickets.subtitle)).toBeInTheDocument();
  });

  it("blocks a page when the user lacks the required permission (403)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/api/auth/me")) {
          return Promise.resolve({ ok: true, json: async () => mockCurrentUser([]) });
        }
        return Promise.reject(new Error(`Unexpected URL: ${url}`));
      }),
    );
    setLoggedInToken();
    render(
      <LocaleProvider>
        <ThemeProvider>
          <AuthProvider>
            <DashboardDataProvider>
              <Dashboard />
            </DashboardDataProvider>
          </AuthProvider>
        </ThemeProvider>
      </LocaleProvider>,
    );

    expect(await screen.findByText("403")).toBeInTheDocument();
    expect(screen.queryByLabelText(tr.common.dashboardSummaryAriaLabel)).not.toBeInTheDocument();
  });
});
