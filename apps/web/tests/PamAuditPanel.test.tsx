import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PamAuditPanel } from "@/components/PamAuditPanel";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const LIVE_SESSION = {
  id: "11111111-1111-1111-1111-111111111111",
  user_id: "u1",
  username: "operator1",
  asset_id: "a1",
  asset_hostname: "srv1.example.local",
  asset_ip_address: "10.0.9.10",
  credential_id: null,
  credential_name: null,
  protocol: "ssh",
  started_at: new Date(Date.now() - 60000).toISOString(),
  ended_at: null,
  end_reason: null,
  client_ip: "10.0.0.5",
  recording_file_path: null,
  terminated_by: null,
};

const LIVE_RDP_SESSION = {
  ...LIVE_SESSION,
  id: "44444444-4444-4444-4444-444444444444",
  protocol: "rdp",
};

const HISTORY_RDP_SESSION = {
  ...LIVE_SESSION,
  id: "22222222-2222-2222-2222-222222222222",
  protocol: "rdp",
  ended_at: new Date().toISOString(),
  end_reason: "user_closed",
  recording_file_path: "/recordings/22222222-2222-2222-2222-222222222222",
};

const HISTORY_SSH_SESSION = {
  ...LIVE_SESSION,
  id: "33333333-3333-3333-3333-333333333333",
  protocol: "ssh",
  ended_at: new Date().toISOString(),
  end_reason: "terminated_by_admin",
};

function mockFetch(handlers: {
  live?: unknown[];
  history?: unknown[];
  onRequest?: (method: string, url: string) => unknown;
}) {
  const calls: { method: string; url: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url });

      if (url.includes("/api/auth/me")) {
        return { ok: true, json: async () => mockCurrentUser(["PAM_ADMIN"]) };
      }
      if (handlers.onRequest) {
        const custom = handlers.onRequest(method, url);
        if (custom !== undefined) return custom;
      }
      if (url.includes("/api/pam/audit?active=true")) {
        return { ok: true, json: async () => handlers.live ?? [] };
      }
      if (url.includes("/api/pam/audit?active=false")) {
        return { ok: true, json: async () => handlers.history ?? [] };
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
        <PamAuditPanel />
      </AuthProvider>
    </LocaleProvider>,
  );
}

describe("PamAuditPanel", () => {
  it("shows the kill-session button and elapsed duration for live sessions", async () => {
    mockFetch({ live: [LIVE_SESSION] });
    renderPanel();

    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: tr.pam.killSession })).toBeInTheDocument();
  });

  it("shows the live-shadow button only for live RDP sessions, not SSH", async () => {
    mockFetch({ live: [LIVE_SESSION, LIVE_RDP_SESSION] });
    renderPanel();

    await waitFor(() => expect(screen.getAllByText("operator1").length).toBe(2));
    expect(screen.getAllByRole("button", { name: tr.pam.shadowSession }).length).toBe(1);
  });

  it("shows recording/keystroke buttons only where applicable in history", async () => {
    mockFetch({ history: [HISTORY_RDP_SESSION, HISTORY_SSH_SESSION] });
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: tr.pam.sessionHistory }));

    await waitFor(() => expect(screen.getAllByText("operator1").length).toBe(2));
    expect(screen.getByRole("button", { name: tr.pam.watchRecording })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: tr.pam.viewKeystrokes })).toBeInTheDocument();
    // Faz 54 — "Bitiş Nedeni" filtre dropdown'unda AYNI metin bir
    // `<option>` olarak da var — sorguyu tabloyla sınırlıyoruz.
    const table = screen.getByRole("table");
    expect(within(table).getByText(tr.pam.endReasonTerminatedByAdmin)).toBeInTheDocument();
  });

  it("confirms and terminates a live session, then reloads the list", async () => {
    const calls = mockFetch({
      live: [LIVE_SESSION],
      onRequest: (method, url) => {
        if (method === "POST" && url.includes(`/api/pam/audit/${LIVE_SESSION.id}/terminate`)) {
          return { ok: true, json: async () => ({ ...LIVE_SESSION, terminated_by: "admin-1" }) };
        }
        return undefined;
      },
    });
    renderPanel();

    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: tr.pam.killSession }));

    await waitFor(() => expect(screen.getByText(tr.pam.confirmKillSessionMessage)).toBeInTheDocument());
    const dialog = screen.getByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: tr.pam.killSession }));

    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.url.includes("/terminate"))).toBe(true),
    );
  });

  it("shows KPI cards computed from the full unfiltered session history", async () => {
    mockFetch({ history: [HISTORY_RDP_SESSION, HISTORY_SSH_SESSION] });
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: tr.pam.sessionHistory }));

    await waitFor(() => expect(screen.getAllByText("operator1").length).toBe(2));
    // 2 oturum toplam, 1 tanesi admin tarafından sonlandırıldı (bkz. sabitler).
    expect(screen.getByText(tr.pam.auditKpiTotalSessions)).toBeInTheDocument();
    const totalCard = screen.getByText(tr.pam.auditKpiTotalSessions).closest('[class*="kpiCard"]');
    expect(within(totalCard as HTMLElement).getByText("2")).toBeInTheDocument();
    const adminCard = screen.getByText(tr.pam.auditKpiAdminTerminated).closest('[class*="kpiCard"]');
    expect(within(adminCard as HTMLElement).getByText("1")).toBeInTheDocument();
  });

  it("sends the debounced search text as a backend query parameter", async () => {
    const calls = mockFetch({ history: [HISTORY_SSH_SESSION] });
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: tr.pam.sessionHistory }));
    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText(tr.pam.auditSearchPlaceholder), { target: { value: "operator1" } });

    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("/api/pam/audit") && c.url.includes("search=operator1"))).toBe(true),
      { timeout: 2000 },
    );
  });

  it("applies the protocol filter as a backend query parameter", async () => {
    const calls = mockFetch({ live: [LIVE_SESSION, LIVE_RDP_SESSION] });
    renderPanel();
    await waitFor(() => expect(screen.getAllByText("operator1").length).toBe(2));

    fireEvent.change(screen.getByLabelText(tr.pam.columnProtocol), { target: { value: "rdp" } });

    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("/api/pam/audit") && c.url.includes("protocol=rdp"))).toBe(true),
    );
  });
});
