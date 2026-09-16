import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PamAccessRequestsPanel } from "@/components/PamAccessRequestsPanel";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const CREDENTIAL = { id: "c1", name: "root-cred", credential_type: "password", username: "root", domain: null, secret_masked: "***", created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
const PENDING_REQUEST = {
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

function mockFetch(handlers: { requests?: unknown[]; credentials?: unknown[]; onRequest?: (method: string, url: string) => unknown }) {
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
      if (url.includes("/api/pam/access-requests")) {
        return { ok: true, json: async () => handlers.requests ?? [] };
      }
      if (url.includes("/api/pam/vault")) {
        return { ok: true, json: async () => handlers.credentials ?? [] };
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
        <PamAccessRequestsPanel />
      </AuthProvider>
    </LocaleProvider>,
  );
}

describe("PamAccessRequestsPanel", () => {
  it("lists pending requests", async () => {
    mockFetch({ requests: [PENDING_REQUEST], credentials: [CREDENTIAL] });
    renderPanel();

    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());
    expect(screen.getByText("acil bakım")).toBeInTheDocument();
  });

  it("approves a request with a selected credential", async () => {
    const calls = mockFetch({
      requests: [PENDING_REQUEST],
      credentials: [CREDENTIAL],
      onRequest: (method, url) => {
        if (method === "POST" && url.includes(`/api/pam/access-requests/${PENDING_REQUEST.id}/approve`)) {
          return { ok: true, json: async () => ({ ...PENDING_REQUEST, status: "approved" }) };
        }
        return undefined;
      },
    });
    renderPanel();

    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: tr.pam.approve }));

    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByRole("combobox"), { target: { value: CREDENTIAL.id } });
    fireEvent.click(within(dialog).getByRole("button", { name: tr.pam.approve }));

    await waitFor(() =>
      expect(
        calls.some((c) => c.method === "POST" && c.url.includes(`/api/pam/access-requests/${PENDING_REQUEST.id}/approve`)),
      ).toBe(true),
    );
  });

  it("rejects a request", async () => {
    const calls = mockFetch({
      requests: [PENDING_REQUEST],
      credentials: [CREDENTIAL],
      onRequest: (method, url) => {
        if (method === "POST" && url.includes(`/api/pam/access-requests/${PENDING_REQUEST.id}/reject`)) {
          return { ok: true, json: async () => ({ ...PENDING_REQUEST, status: "rejected" }) };
        }
        return undefined;
      },
    });
    renderPanel();

    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: tr.pam.reject }));

    await waitFor(() =>
      expect(
        calls.some((c) => c.method === "POST" && c.url.includes(`/api/pam/access-requests/${PENDING_REQUEST.id}/reject`)),
      ).toBe(true),
    );
  });
});
