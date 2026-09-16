import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentDownloadPanel } from "@/components/AgentDownloadPanel";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPanel() {
  return render(
    <LocaleProvider>
      <AgentDownloadPanel />
    </LocaleProvider>,
  );
}

const NOT_AVAILABLE = { available: false, version: null, filename: null, size_bytes: null, built_at: null };

function mockDownloadInfo(info: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => info }));
}

/** Kullanıcı isteğiyle düz CLI EXE indirmesi panelden KALDIRILDI (bkz.
 * component docstring'i) — panel artık yalnızca Windows Servisi
 * paketini (`/download/windows-service/info`) gösteriyor. */
describe("AgentDownloadPanel", () => {
  it("shows an honest 'not built' state — never a fake download link", async () => {
    mockDownloadInfo(NOT_AVAILABLE);
    renderPanel();

    expect(await screen.findByText(tr.settings.download.serviceNotBuilt)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: tr.settings.download.serviceButton })).not.toBeInTheDocument();
  });

  it("shows the real download button, version, and file size when built", async () => {
    mockDownloadInfo({
      available: true,
      version: "1.0.0",
      filename: "itops-agent.exe",
      size_bytes: 9_906_373,
      built_at: "2026-01-01T00:00:00Z",
    });
    renderPanel();

    const link = await screen.findByRole("link", { name: tr.settings.download.serviceButton });
    expect(link).toHaveAttribute("href", "/api/agents/download/windows-service");
    expect(screen.getByText("1.0.0")).toBeInTheDocument();
    expect(screen.getByText("9.4 MB")).toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) }));
    renderPanel();

    expect(await screen.findByText(tr.settings.download.loadError)).toBeInTheDocument();
  });

  it("never shows a download link before real availability is confirmed", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    renderPanel();

    expect(screen.queryByRole("link", { name: tr.settings.download.serviceButton })).not.toBeInTheDocument();
  });
});
