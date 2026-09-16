import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentRetentionPolicyPanel } from "@/components/AgentRetentionPolicyPanel";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPanel() {
  return render(
    <LocaleProvider>
      <AgentRetentionPolicyPanel />
    </LocaleProvider>,
  );
}

function stubFetch(policy: { enabled: boolean; retention_days: number }) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.includes("/api/agents/retention-policy")) {
        return Promise.resolve({ ok: true, json: async () => policy } as Response);
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    }),
  );
}

describe("AgentRetentionPolicyPanel", () => {
  it("shows the current policy — disabled by default, 30 days", async () => {
    stubFetch({ enabled: false, retention_days: 30 });
    renderPanel();

    const checkbox = (await screen.findByLabelText(tr.agents.retentionPolicy.enabledLabel)) as HTMLInputElement;
    expect(checkbox.checked).toBe(false);
    expect(screen.getByDisplayValue("30")).toBeInTheDocument();
  });

  it("toggling the checkbox immediately saves the new policy", async () => {
    stubFetch({ enabled: false, retention_days: 30 });
    renderPanel();
    const checkbox = (await screen.findByLabelText(tr.agents.retentionPolicy.enabledLabel)) as HTMLInputElement;

    const fetchMock = vi.mocked(global.fetch);
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve({ ok: true, json: async () => ({ enabled: true, retention_days: 30 }) } as Response),
    );
    fireEvent.click(checkbox);

    await waitFor(() => {
      const putCall = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PUT");
      expect(putCall).toBeTruthy();
    });
  });

  it("selecting a preset saves the new retention_days", async () => {
    stubFetch({ enabled: true, retention_days: 30 });
    renderPanel();
    await screen.findByLabelText(tr.agents.retentionPolicy.enabledLabel);

    const fetchMock = vi.mocked(global.fetch);
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve({ ok: true, json: async () => ({ enabled: true, retention_days: 7 }) } as Response),
    );
    fireEvent.click(screen.getByRole("button", { name: tr.agents.retentionPolicy.presets["7"] }));

    await waitFor(() => {
      const putCall = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PUT");
      expect(putCall).toBeTruthy();
      const body = JSON.parse(String((putCall![1] as RequestInit).body));
      expect(body.retention_days).toBe(7);
    });
  });

  it("shows an error state when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: false, status: 503, json: async () => ({}) })));
    renderPanel();

    expect(await screen.findByText(tr.agents.retentionPolicy.loadError)).toBeInTheDocument();
  });
});
