import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PamServerGroupsPanel } from "@/components/PamServerGroupsPanel";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const GROUP_LINUX = {
  id: "g1",
  name: "Linux Sunucuları",
  description: "Tüm Linux hostlar",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};
const ASSET = { id: "a1", ip_address: "10.0.9.10", hostname: "srv1.example.local" };

function mockFetch(handlers: {
  groups?: unknown[];
  assets?: unknown[];
  groupAssets?: unknown[];
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
      if (/\/api\/pam\/server-groups\/[^/]+\/assets/.test(url)) {
        return { ok: true, json: async () => handlers.groupAssets ?? [] };
      }
      if (url.includes("/api/pam/server-groups")) {
        return { ok: true, json: async () => handlers.groups ?? [] };
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
        <PamServerGroupsPanel />
      </AuthProvider>
    </LocaleProvider>,
  );
}

describe("PamServerGroupsPanel", () => {
  it("lists server groups and creates a new one", async () => {
    const calls = mockFetch({
      groups: [GROUP_LINUX],
      onRequest: (method, url) => {
        if (method === "POST" && url.includes("/api/pam/server-groups")) {
          return { ok: true, json: async () => ({ ...GROUP_LINUX, id: "g2", name: "DB Sunucuları" }) };
        }
        return undefined;
      },
    });
    renderPanel();

    await waitFor(() => expect(screen.getByText("🗂️ Linux Sunucuları")).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText(tr.pam.newGroupNamePlaceholder), { target: { value: "DB Sunucuları" } });
    fireEvent.click(screen.getByRole("button", { name: tr.pam.create }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.includes("/api/pam/server-groups"))).toBe(true));
  });

  it("opens the manage-assets modal and toggles a group membership", async () => {
    const calls = mockFetch({ groups: [GROUP_LINUX], assets: [ASSET], groupAssets: [] });
    renderPanel();

    await waitFor(() => expect(screen.getByText("🗂️ Linux Sunucuları")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: tr.pam.manageAssets }));

    await waitFor(() => expect(screen.getByText("srv1.example.local")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("checkbox"));

    await waitFor(() =>
      expect(
        calls.some((c) => c.method === "PUT" && c.url.includes(`/api/pam/server-groups/${GROUP_LINUX.id}/assets/${ASSET.id}`)),
      ).toBe(true),
    );
  });

  it("deletes a server group", async () => {
    const calls = mockFetch({
      groups: [GROUP_LINUX],
      onRequest: (method, url) => {
        if (method === "DELETE" && url.includes(`/api/pam/server-groups/${GROUP_LINUX.id}`)) {
          return { ok: true, status: 204, json: async () => null };
        }
        return undefined;
      },
    });
    renderPanel();

    await waitFor(() => expect(screen.getByText("🗂️ Linux Sunucuları")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: tr.pam.delete }));

    await waitFor(() => expect(screen.getByRole("alertdialog")).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole("button", { name: tr.pam.delete }).slice(-1)[0]);

    await waitFor(() =>
      expect(calls.some((c) => c.method === "DELETE" && c.url.includes(`/api/pam/server-groups/${GROUP_LINUX.id}`))).toBe(true),
    );
  });
});
