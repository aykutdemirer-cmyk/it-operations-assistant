import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MyAccessPanel } from "@/components/MyAccessPanel";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const ASSET = { id: "a1", ip_address: "10.0.9.10", hostname: "srv1.example.local" };
const ONLINE_AUTHORIZED_ASSET = {
  asset_id: "a1",
  asset_hostname: "srv1.example.local",
  asset_ip_address: "10.0.9.10",
  allow_rdp: false,
  allow_ssh: true,
  max_session_duration_mins: 60,
  valid_until: null,
  is_online: true,
  active_sessions_count: 2,
};
const OFFLINE_AUTHORIZED_ASSET = {
  asset_id: "a2",
  asset_hostname: "srv2.example.local",
  asset_ip_address: "10.0.9.11",
  allow_rdp: true,
  allow_ssh: false,
  max_session_duration_mins: 60,
  valid_until: null,
  is_online: false,
  active_sessions_count: 0,
};
const MY_REQUEST = {
  id: "r1",
  requester_id: "u1",
  requester_username: "operator1",
  asset_id: "a1",
  asset_hostname: "srv1.example.local",
  asset_ip_address: "10.0.9.10",
  tag_id: null,
  tag_name: null,
  server_group_id: null,
  server_group_name: null,
  protocol: "ssh",
  business_reason: "acil bakım",
  requested_duration_mins: 60,
  status: "pending",
  reviewed_by: null,
  reviewed_by_username: null,
  reviewed_at: null,
  review_note: null,
  created_at: new Date().toISOString(),
};
const OTHER_REQUEST = { ...MY_REQUEST, id: "r2", asset_hostname: "srv2.example.local", business_reason: "yazılım kurulumu", status: "approved" };

function mockFetch(handlers: {
  myAccess?: unknown[];
  requests?: unknown[];
  assets?: unknown[];
  onRequest?: (method: string, url: string) => unknown;
}) {
  const calls: { method: string; url: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url });

      if (url.includes("/api/auth/me")) {
        return { ok: true, json: async () => mockCurrentUser(["PAM_ACCESS"]) };
      }
      if (handlers.onRequest) {
        const custom = handlers.onRequest(method, url);
        if (custom !== undefined) return custom;
      }
      if (url.includes("/api/pam/access-requests/mine")) {
        return { ok: true, json: async () => handlers.requests ?? [] };
      }
      if (url.includes("/api/pam/my-access")) {
        return { ok: true, json: async () => handlers.myAccess ?? [] };
      }
      if (url.includes("/api/assets")) {
        return { ok: true, json: async () => handlers.assets ?? [] };
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
        <MyAccessPanel />
      </AuthProvider>
    </LocaleProvider>,
  );
}

describe("MyAccessPanel", () => {
  it("shows empty state when no authorized servers exist", async () => {
    mockFetch({ myAccess: [], requests: [], assets: [] });
    renderPanel();

    await waitFor(() => expect(screen.getByText(tr.pam.myAccessEmpty)).toBeInTheDocument());
  });

  it("lists the user's own access requests", async () => {
    mockFetch({ myAccess: [], requests: [MY_REQUEST], assets: [] });
    renderPanel();

    await waitFor(() => expect(screen.getByText("srv1.example.local")).toBeInTheDocument());
    expect(screen.getByText("acil bakım")).toBeInTheDocument();
  });

  it("submits a new access request", async () => {
    const calls = mockFetch({
      myAccess: [],
      requests: [],
      assets: [ASSET],
      onRequest: (method, url) => {
        if (method === "POST" && url.includes("/api/pam/access-requests") && !url.includes("mine")) {
          return { ok: true, status: 201, json: async () => ({ ...MY_REQUEST } ) };
        }
        return undefined;
      },
    });
    renderPanel();

    await waitFor(() => expect(screen.getByText(tr.pam.myAccessEmpty)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: tr.pam.requestAccess }));

    await waitFor(() => expect(screen.getByText("srv1.example.local")).toBeInTheDocument());
    fireEvent.change(screen.getAllByRole("combobox")[0], { target: { value: ASSET.id } });
    fireEvent.change(screen.getByPlaceholderText(tr.pam.requestBusinessReasonPlaceholder), {
      target: { value: "acil bakım" },
    });
    fireEvent.click(screen.getByRole("button", { name: tr.pam.create }));

    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.url.includes("/api/pam/access-requests") && !c.url.includes("mine"))).toBe(
        true,
      ),
    );
  });

  it("shows KPI cards derived from the loaded data", async () => {
    mockFetch({
      myAccess: [ONLINE_AUTHORIZED_ASSET, OFFLINE_AUTHORIZED_ASSET],
      requests: [MY_REQUEST, OTHER_REQUEST],
      assets: [],
    });
    renderPanel();

    await waitFor(() => expect(screen.getAllByText("srv1.example.local").length).toBeGreaterThan(0));
    const kpiLabelEls = screen.getAllByText(tr.pam.kpiMyServers);
    const myServersCard = kpiLabelEls.find((el) => el.closest('[class*="kpiCard"]'))!.closest('[class*="kpiCard"]')!;
    expect(myServersCard).toHaveTextContent("2"); // Yetkili Sunucularım (2)
    expect(screen.getByText(tr.pam.kpiActiveRequests)).toBeInTheDocument();
    expect(screen.getByText("1/2")).toBeInTheDocument(); // Erişilebilir Sunucular (1 online / 2 toplam)
  });

  it("shows online/offline availability and active session badges", async () => {
    mockFetch({ myAccess: [ONLINE_AUTHORIZED_ASSET, OFFLINE_AUTHORIZED_ASSET], requests: [], assets: [] });
    renderPanel();

    await waitFor(() => expect(screen.getByText("srv1.example.local")).toBeInTheDocument());
    expect(screen.getByText(tr.pam.onlineLabel)).toBeInTheDocument();
    expect(screen.getByText(tr.pam.offlineLabel)).toBeInTheDocument();
    expect(screen.getByText(tr.pam.activeConnections(2))).toBeInTheDocument();
    expect(screen.getByText(tr.pam.idleLabel)).toBeInTheDocument();
  });

  it("filters requests by search text", async () => {
    mockFetch({ myAccess: [], requests: [MY_REQUEST, OTHER_REQUEST], assets: [] });
    renderPanel();

    await waitFor(() => expect(screen.getByText("acil bakım")).toBeInTheDocument());
    expect(screen.getByText("yazılım kurulumu")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(tr.pam.requestsSearchPlaceholder), { target: { value: "yazılım" } });

    await waitFor(() => expect(screen.queryByText("acil bakım")).not.toBeInTheDocument());
    expect(screen.getByText("yazılım kurulumu")).toBeInTheDocument();
  });
});
