import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ScheduledScansPanel } from "@/components/ScheduledScansPanel";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const SCHEDULE = {
  id: "s1",
  cidr: "10.0.0.0/24",
  interval_hours: 24,
  enabled: true,
  last_run_at: null,
  last_run_status: null,
  last_run_error: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function mockFetch(handlers: {
  schedules?: unknown[];
  onRequest?: (method: string, url: string, body?: string) => unknown;
}) {
  const calls: { method: string; url: string; body?: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = init?.body as string | undefined;
      calls.push({ method, url, body });

      if (url.includes("/api/auth/me")) {
        return { ok: true, json: async () => mockCurrentUser([], { role: "ADMIN" }) };
      }
      if (handlers.onRequest) {
        const custom = handlers.onRequest(method, url, body);
        if (custom !== undefined) return custom;
      }
      if (url.endsWith("/api/discovery/schedules") && method === "GET") {
        return { ok: true, json: async () => handlers.schedules ?? [] };
      }
      return Promise.reject(new Error(`Unexpected request: ${method} ${url}`));
    }),
  );
  return calls;
}

function renderPanel() {
  setLoggedInToken();
  return render(
    <LocaleProvider>
      <AuthProvider>
        <ScheduledScansPanel />
      </AuthProvider>
    </LocaleProvider>,
  );
}

const s = tr.settings.scheduledScans;

describe("ScheduledScansPanel", () => {
  it("shows an empty state when there are no schedules", async () => {
    mockFetch({ schedules: [] });
    renderPanel();
    expect(await screen.findByText(s.empty)).toBeInTheDocument();
  });

  it("creates a new schedule via POST with cidr + interval_hours", async () => {
    const calls = mockFetch({
      schedules: [],
      onRequest: (method, url) => {
        if (method === "POST" && url.endsWith("/api/discovery/schedules")) {
          return { ok: true, status: 201, json: async () => SCHEDULE };
        }
        return undefined;
      },
    });
    renderPanel();
    await waitFor(() => expect(screen.getByText(s.empty)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(s.cidrPlaceholder), { target: { value: "10.0.0.0/24" } });
    fireEvent.change(screen.getByLabelText(s.intervalLabel), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: s.add }));

    await waitFor(() => {
      const post = calls.find((c) => c.method === "POST");
      expect(post).toBeTruthy();
      expect(JSON.parse(post!.body!)).toMatchObject({ cidr: "10.0.0.0/24", interval_hours: 12, enabled: true });
    });
  });

  it("lists an existing schedule with its interval and last-run state", async () => {
    mockFetch({ schedules: [SCHEDULE] });
    renderPanel();

    expect(await screen.findByText("10.0.0.0/24")).toBeInTheDocument();
    expect(screen.getByText("24h")).toBeInTheDocument();
    expect(screen.getByText(s.neverRun)).toBeInTheDocument();
  });

  it("toggles a schedule's enabled state via PUT", async () => {
    const calls = mockFetch({
      schedules: [SCHEDULE],
      onRequest: (method, url) => {
        if (method === "PUT" && url.includes("/api/discovery/schedules/s1")) {
          return { ok: true, json: async () => ({ ...SCHEDULE, enabled: false }) };
        }
        return undefined;
      },
    });
    renderPanel();
    await waitFor(() => expect(screen.getByText("10.0.0.0/24")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: s.enabled }));

    await waitFor(() => {
      const put = calls.find((c) => c.method === "PUT");
      expect(put).toBeTruthy();
      expect(JSON.parse(put!.body!)).toEqual({ enabled: false });
    });
  });

  it("deletes a schedule via DELETE", async () => {
    const calls = mockFetch({
      schedules: [SCHEDULE],
      onRequest: (method, url) => {
        if (method === "DELETE" && url.includes("/api/discovery/schedules/s1")) {
          return { ok: true, status: 204, json: async () => null };
        }
        return undefined;
      },
    });
    renderPanel();
    await waitFor(() => expect(screen.getByText("10.0.0.0/24")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: s.delete }));

    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });
});
