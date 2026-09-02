/**
 * Her sayfanın gerçek route/dosyasının (app/**\/page.tsx) hatasız
 * render olduğunu ve o sayfaya özgü gerçek bir başlık/metin
 * gösterdiğini doğrulayan smoke testleri (bkz. Faz — "PAGE B/E").
 * Ayrıntılı davranış (filtreler, etkileşimler) ilgili component'in
 * kendi test dosyasında zaten kapsanıyor — burada yalnızca "doğru
 * component doğru route'a bağlandı mı" doğrulanır.
 */
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/",
}));

import Dashboard from "@/app/page";
import DiscoveryPage from "@/app/discovery/page";
import AssetsPage from "@/app/assets/page";
import TopologyPage from "@/app/topology/page";
import ScansPage from "@/app/scans/page";
import AlertsPage from "@/app/alerts/page";
import MonitoringPage from "@/app/monitoring/page";
import SettingsPage from "@/app/settings/page";
import { DashboardDataProvider } from "@/lib/DashboardDataProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { ThemeProvider } from "@/lib/theme/ThemeProvider";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockAssetsAndScans() {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
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
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    }),
  );
}

function renderPage(ui: React.ReactElement) {
  mockAssetsAndScans();
  return render(
    <LocaleProvider>
      <ThemeProvider>
        <DashboardDataProvider>{ui}</DashboardDataProvider>
      </ThemeProvider>
    </LocaleProvider>,
  );
}

describe("Pages", () => {
  it("renders the Dashboard page with its summary region", () => {
    renderPage(<Dashboard />);
    expect(screen.getByLabelText(tr.common.dashboardSummaryAriaLabel)).toBeInTheDocument();
  });

  it("renders the Discovery page", () => {
    renderPage(<DiscoveryPage />);
    expect(screen.getByText(tr.discovery.title)).toBeInTheDocument();
  });

  it("renders the Assets page", () => {
    renderPage(<AssetsPage />);
    expect(screen.getByText(tr.assets.title)).toBeInTheDocument();
  });

  it("renders the Topology page", async () => {
    renderPage(<TopologyPage />);
    expect(await screen.findByText(tr.topology.title)).toBeInTheDocument();
  });

  it("renders the Scans page", () => {
    renderPage(<ScansPage />);
    expect(screen.getByText(tr.scans.title)).toBeInTheDocument();
  });

  it("renders the Alerts page", () => {
    renderPage(<AlertsPage />);
    expect(screen.getByText(tr.alerts.title)).toBeInTheDocument();
  });

  it("renders the Monitoring page", () => {
    renderPage(<MonitoringPage />);
    expect(screen.getByText(tr.monitoring.title)).toBeInTheDocument();
  });

  it("renders the Settings page", () => {
    renderPage(<SettingsPage />);
    expect(screen.getByText(tr.settings.title)).toBeInTheDocument();
  });
});
