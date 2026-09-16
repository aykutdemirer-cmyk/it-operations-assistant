import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PamUsersPanel } from "@/components/PamUsersPanel";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const LOCAL_USER = {
  id: "11111111-1111-1111-1111-111111111111",
  username: "operator1",
  role: "OPERATOR",
  full_name: "Operatör Bir",
  is_active: true,
  ad_username: null,
  permissions: [],
  ticket_role: "REQUESTER",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const AD_USER = {
  id: "ad-1",
  distinguished_name: "CN=Jane Doe,DC=lab,DC=local",
  username: "jdoe",
  display_name: "Jane Doe",
  email: "jdoe@lab.local",
  synced_at: "2026-01-01T00:00:00Z",
};

function mockFetch(handlers: {
  users?: unknown[];
  adUsers?: unknown[];
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
      if (url.includes("/api/settings/ldap/users")) {
        return { ok: true, json: async () => handlers.adUsers ?? [] };
      }
      if (method === "GET" && url.includes("/api/pam/users")) {
        return { ok: true, json: async () => handlers.users ?? [] };
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
        <PamUsersPanel />
      </AuthProvider>
    </LocaleProvider>,
  );
}

describe("PamUsersPanel", () => {
  it("shows the AD-synced badge for users already linked to an AD account", async () => {
    mockFetch({ users: [{ ...LOCAL_USER, ad_username: "jdoe" }], adUsers: [AD_USER] });
    renderPanel();

    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());
    expect(screen.getByText(tr.pam.adSyncedBadge)).toBeInTheDocument();
  });

  it("switches the create form to the AD picker and imports via createPamUserFromAd", async () => {
    const calls = mockFetch({
      users: [LOCAL_USER],
      adUsers: [AD_USER],
      onRequest: (method, url) => {
        if (method === "POST" && url.includes("/api/pam/users/from-ad")) {
          return { ok: true, json: async () => ({ ...LOCAL_USER, id: "new-1", username: "jdoe", ad_username: "jdoe" }) };
        }
        return undefined;
      },
    });
    renderPanel();

    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: tr.pam.newUser }));

    fireEvent.change(screen.getByLabelText(new RegExp(tr.pam.userSourceLabel)), { target: { value: "ad" } });
    fireEvent.change(screen.getByLabelText(new RegExp(tr.pam.selectAdUserLabel)), { target: { value: "jdoe" } });
    fireEvent.click(screen.getByRole("button", { name: tr.pam.importFromAd }));

    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.url.includes("/api/pam/users/from-ad"))).toBe(true),
    );
  });

  it("shows the empty-state message when no AD users are synced yet", async () => {
    mockFetch({ users: [LOCAL_USER], adUsers: [] });
    renderPanel();

    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: tr.pam.newUser }));
    fireEvent.change(screen.getByLabelText(new RegExp(tr.pam.userSourceLabel)), { target: { value: "ad" } });

    expect(screen.getByText(tr.pam.noSyncedAdUsers)).toBeInTheDocument();
  });

  it("updates a user's ticket role inline via updatePamUser (Faz 65)", async () => {
    const calls = mockFetch({
      users: [LOCAL_USER],
      adUsers: [],
      onRequest: (method, url) => {
        if (method === "PUT" && url.includes("/api/pam/users/")) {
          return { ok: true, json: async () => ({ ...LOCAL_USER, ticket_role: "TECHNICIAN" }) };
        }
        return undefined;
      },
    });
    renderPanel();

    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());
    const select = screen.getByLabelText(`operator1 — ${tr.tickets.colTicketRole}`);
    expect(select).toHaveValue("REQUESTER");
    fireEvent.change(select, { target: { value: "TECHNICIAN" } });

    await waitFor(() => {
      const put = calls.find((c) => c.method === "PUT" && c.url.includes("/api/pam/users/"));
      expect(put).toBeTruthy();
    });
  });
});
