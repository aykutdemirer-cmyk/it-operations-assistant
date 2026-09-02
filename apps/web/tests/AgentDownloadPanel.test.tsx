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

function mockDownloadInfo(info: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => info }));
}

describe("AgentDownloadPanel", () => {
  it("shows an honest 'not built' state — never a fake download link", async () => {
    mockDownloadInfo({ available: false, version: null, filename: null, size_bytes: null, built_at: null });
    renderPanel();

    expect(await screen.findByText(tr.settings.download.notBuilt)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: tr.settings.download.windowsButton })).not.toBeInTheDocument();
  });

  it("shows the real download button, version, and file size when built", async () => {
    mockDownloadInfo({
      available: true,
      version: "1.0.0",
      filename: "IT-Operations-Agent-1.0.0.exe",
      size_bytes: 9_311_292,
      built_at: "2026-01-01T00:00:00Z",
    });
    renderPanel();

    const link = await screen.findByRole("link", { name: tr.settings.download.windowsButton });
    expect(link).toHaveAttribute("href", "http://localhost:8000/api/agents/download/windows");
    expect(screen.getByText("1.0.0")).toBeInTheDocument();
    expect(screen.getByText("8.9 MB")).toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) }));
    renderPanel();

    expect(await screen.findByText(tr.settings.download.loadError)).toBeInTheDocument();
  });

  it("never shows a download link before real availability is confirmed", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    renderPanel();

    expect(screen.queryByRole("link", { name: tr.settings.download.windowsButton })).not.toBeInTheDocument();
  });
});
