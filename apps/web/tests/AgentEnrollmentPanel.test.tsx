import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentEnrollmentPanel } from "@/components/AgentEnrollmentPanel";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPanel() {
  return render(
    <LocaleProvider>
      <AgentEnrollmentPanel />
    </LocaleProvider>,
  );
}

function mockFetch(handlers: { active?: unknown[]; onPost?: () => unknown }) {
  const active = handlers.active ?? [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/agents/enrollment-codes") && method === "GET") {
        return Promise.resolve({ ok: true, json: async () => active });
      }
      if (url.includes("/api/agents/enrollment-codes") && method === "POST") {
        if (handlers.onPost) return Promise.resolve(handlers.onPost());
        return Promise.resolve({
          ok: true,
          json: async () => ({ code: "ABC-DEF-123", expires_at: new Date(Date.now() + 600_000).toISOString() }),
        });
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    }),
  );
}

describe("AgentEnrollmentPanel", () => {
  it("shows 'no active codes' when none exist", async () => {
    mockFetch({ active: [] });
    renderPanel();

    expect(await screen.findByText(tr.settings.enrollment.noActiveCodes)).toBeInTheDocument();
  });

  it("lists real active codes with their remaining time", async () => {
    mockFetch({
      active: [
        { code: "XYZ-987-QWE", created_at: new Date().toISOString(), expires_at: new Date(Date.now() + 300_000).toISOString() },
      ],
    });
    renderPanel();

    expect(await screen.findByText("XYZ-987-QWE")).toBeInTheDocument();
  });

  it("generates a new code and displays it with a countdown", async () => {
    mockFetch({ active: [] });
    renderPanel();

    await screen.findByText(tr.settings.enrollment.noActiveCodes);
    fireEvent.click(screen.getByText(tr.settings.enrollment.generateButton));

    expect(await screen.findByText("ABC-DEF-123")).toBeInTheDocument();
    expect(screen.getByText(tr.settings.enrollment.singleUseHint)).toBeInTheDocument();
  });

  it("shows a real error message when generation fails", async () => {
    mockFetch({
      active: [],
      onPost: () => ({ ok: false, status: 503, json: async () => ({ detail: "Backend erişilemedi" }) }),
    });
    renderPanel();

    await screen.findByText(tr.settings.enrollment.noActiveCodes);
    fireEvent.click(screen.getByText(tr.settings.enrollment.generateButton));

    expect(await screen.findByText("Backend erişilemedi")).toBeInTheDocument();
  });

  it("never shows a value that looks like a real credential label", async () => {
    mockFetch({ active: [] });
    renderPanel();

    await screen.findByText(tr.settings.enrollment.noActiveCodes);
    expect(screen.queryByText(/password|token değeri/i)).not.toBeInTheDocument();
  });
});
