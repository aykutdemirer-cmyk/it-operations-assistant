import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsPanel } from "@/components/SettingsPanel";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { ThemeProvider } from "@/lib/theme/ThemeProvider";

beforeEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

function mockHealthEndpoints(overrides: Record<string, { ok: boolean; body: unknown }> = {}) {
  const defaults: Record<string, { ok: boolean; body: unknown }> = {
    "/api/health": { ok: true, body: { status: "ok" } },
    "/api/health/db": { ok: true, body: { database: "ok" } },
    "/api/health/snmp": { ok: true, body: { snmp: "not_configured" } },
    "/api/agents": { ok: true, body: [] },
    "/api/snmp/profiles": { ok: true, body: [] },
    ...overrides,
  };

  // Uzun path'ler önce kontrol edilmeli — `/api/health/db`,
  // `/api/health`'in de bir substring'i olduğu için sıralama önemli.
  const orderedPaths = Object.keys(defaults).sort((a, b) => b.length - a.length);

  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const path = orderedPaths.find((candidate) => url.includes(candidate));
      if (!path) return Promise.reject(new Error(`Unexpected URL: ${url}`));
      const { ok, body } = defaults[path];
      return Promise.resolve({ ok, json: async () => body });
    }),
  );
}

function renderSettings() {
  return render(
    <LocaleProvider>
      <ThemeProvider>
        <SettingsPanel />
      </ThemeProvider>
    </LocaleProvider>,
  );
}

describe("SettingsPanel", () => {
  it("shows Dark selected by default and switches to Light", () => {
    mockHealthEndpoints();
    renderSettings();

    const darkButton = screen.getByRole("button", { name: tr.settings.appearanceDark });
    expect(darkButton).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: tr.settings.appearanceLight }));

    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("shows Türkçe selected by default and switches to English", () => {
    mockHealthEndpoints();
    renderSettings();

    const trButton = screen.getByRole("button", { name: tr.settings.languageTr });
    expect(trButton).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: tr.settings.languageEn }));

    expect(document.documentElement.lang).toBe("en");
  });

  it("shows connected status for backend and database when healthy", async () => {
    mockHealthEndpoints();
    renderSettings();

    await waitFor(() =>
      expect(screen.getAllByText(tr.settings.connected).length).toBeGreaterThan(0),
    );
  });

  it("shows disconnected status when the database is unreachable", async () => {
    mockHealthEndpoints({
      "/api/health/db": { ok: false, body: {} },
    });
    renderSettings();

    await waitFor(() =>
      expect(screen.getAllByText(tr.settings.disconnected).length).toBeGreaterThan(0),
    );
  });

  it("always shows SNMP as not configured — no real agent exists", async () => {
    mockHealthEndpoints();
    renderSettings();

    await waitFor(() =>
      expect(screen.getByText(tr.settings.notConfigured)).toBeInTheDocument(),
    );
  });

  it("shows the real registered agent count from GET /api/agents", async () => {
    mockHealthEndpoints({
      "/api/agents": {
        ok: true,
        body: [
          { id: "1", hostname: "a", os: "windows", os_version: null, agent_version: "1.0.0", asset_id: null, status: "unknown", registered_at: "2026-01-01T00:00:00Z", last_heartbeat_at: null },
          { id: "2", hostname: "b", os: "linux", os_version: null, agent_version: "1.0.0", asset_id: null, status: "unknown", registered_at: "2026-01-01T00:00:00Z", last_heartbeat_at: null },
        ],
      },
    });
    renderSettings();

    await waitFor(() => expect(screen.getByText("2")).toBeInTheDocument());
  });

  it("renders the SNMP Configuration Center section", async () => {
    mockHealthEndpoints();
    renderSettings();

    expect(screen.getAllByText(tr.settings.snmpConfig.sectionTitle).length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByText(tr.settings.snmpConfig.noProfiles)).toBeInTheDocument());
  });
});
