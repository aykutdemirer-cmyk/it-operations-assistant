import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ArchivedAgentsList } from "@/components/ArchivedAgentsList";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPanel() {
  return render(
    <LocaleProvider>
      <ArchivedAgentsList />
    </LocaleProvider>,
  );
}

const ARCHIVED_MANUAL = {
  id: "aaaaaaaa-1111-1111-1111-111111111111",
  hostname: "old-server",
  os: "windows",
  os_version: "Windows Server 2022",
  local_ip: "10.0.213.40",
  registered_at: "2026-08-01T00:00:00Z",
  last_heartbeat_at: "2026-08-27T00:00:00Z",
  archived_at: "2026-08-28T00:00:00Z",
  archived_reason: "manual",
  archived_after_inactive_days: null,
  active_duration_seconds: 3600 * 24 * 2,
};

const ARCHIVED_INACTIVITY = {
  ...ARCHIVED_MANUAL,
  id: "bbbbbbbb-2222-2222-2222-222222222222",
  hostname: "ghost-host",
  archived_reason: "inactivity",
  archived_after_inactive_days: 30,
  active_duration_seconds: null,
};

function stubFetch(agents: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.includes("/api/agents/archived")) {
        return Promise.resolve({ ok: true, json: async () => agents });
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    }),
  );
}

describe("ArchivedAgentsList", () => {
  it("shows the empty state when nothing is archived", async () => {
    stubFetch([]);
    renderPanel();

    expect(await screen.findByText(tr.agents.archived.emptyTitle)).toBeInTheDocument();
  });

  it("shows manual deletion reason", async () => {
    stubFetch([ARCHIVED_MANUAL]);
    renderPanel();

    expect(await screen.findByText("old-server")).toBeInTheDocument();
    expect(screen.getByText(tr.agents.archived.reasonManual)).toBeInTheDocument();
  });

  it("shows inactivity deletion reason with the day count", async () => {
    stubFetch([ARCHIVED_INACTIVITY]);
    renderPanel();

    expect(await screen.findByText("ghost-host")).toBeInTheDocument();
    expect(screen.getByText(tr.agents.archived.reasonInactivity.replace("{days}", "30"))).toBeInTheDocument();
  });

  it("restores an archived agent", async () => {
    stubFetch([ARCHIVED_MANUAL]);
    renderPanel();
    await screen.findByText("old-server");

    const fetchMock = vi.mocked(global.fetch);
    fetchMock.mockImplementationOnce(() => Promise.resolve({ ok: true, json: async () => ({ id: ARCHIVED_MANUAL.id }) } as Response));
    fetchMock.mockImplementationOnce(() => Promise.resolve({ ok: true, json: async () => [] } as Response));

    fireEvent.click(screen.getByRole("button", { name: tr.agents.archived.restore }));

    await waitFor(() => {
      const restoreCall = fetchMock.mock.calls.find(([url]) => String(url).includes(`/api/agents/${ARCHIVED_MANUAL.id}/restore`));
      expect(restoreCall).toBeTruthy();
    });
  });

  it("shows an error state when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: false, status: 503, json: async () => ({}) })));
    renderPanel();

    expect(await screen.findByText(tr.agents.archived.loadError)).toBeInTheDocument();
  });
});
