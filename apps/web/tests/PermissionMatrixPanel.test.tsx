import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PermissionMatrixPanel } from "@/components/PermissionMatrixPanel";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const USER_A = {
  id: "u1",
  username: "operator1",
  role: "OPERATOR",
  full_name: null,
  is_active: true,
  ad_username: null,
  permissions: ["DASHBOARD_VIEW", "PAM_ACCESS"],
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

function mockFetch(handlers: { users?: unknown[]; onRequest?: (method: string, url: string) => unknown }) {
  const calls: { method: string; url: string; body?: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: init?.body as string | undefined });

      if (url.includes("/api/auth/me")) {
        return { ok: true, json: async () => mockCurrentUser(["PAM_ADMIN"]) };
      }
      if (handlers.onRequest) {
        const custom = handlers.onRequest(method, url);
        if (custom !== undefined) return custom;
      }
      if (url.includes("/api/pam/users")) {
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
        <PermissionMatrixPanel />
      </AuthProvider>
    </LocaleProvider>,
  );
}

describe("PermissionMatrixPanel", () => {
  it("renders the user x permission grid", async () => {
    mockFetch({ users: [USER_A] });
    renderPanel();

    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());
    // PAM_ACCESS zaten işaretli — kullanıcı adı satırındaki tüm checkbox'lar arasından
    // en az biri işaretli olmalı.
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    expect(checkboxes.some((c) => c.checked)).toBe(true);
  });

  it("toggling a cell sends the user's full updated permission list", async () => {
    const calls = mockFetch({
      users: [USER_A],
      onRequest: (method, url) => {
        if (method === "PUT" && url.includes(`/api/pam/users/${USER_A.id}/permissions`)) {
          return { ok: true, json: async () => ({ ...USER_A, permissions: [...USER_A.permissions, "ASSETS_VIEW"] }) };
        }
        return undefined;
      },
    });
    renderPanel();

    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());
    const assetsCheckbox = screen.getByRole("checkbox", { name: `operator1 — ${tr.pam.permissionAssetsView}` });
    expect((assetsCheckbox as HTMLInputElement).checked).toBe(false);
    fireEvent.click(assetsCheckbox);

    await waitFor(() =>
      expect(calls.some((c) => c.method === "PUT" && c.url.includes(`/api/pam/users/${USER_A.id}/permissions`))).toBe(true),
    );
    const putCall = calls.find((c) => c.method === "PUT" && c.url.includes(`/api/pam/users/${USER_A.id}/permissions`));
    const body = JSON.parse(putCall!.body!);
    expect(body.permissions).toEqual(expect.arrayContaining([...USER_A.permissions, "ASSETS_VIEW"]));
  });

  it("reverts the checkbox on a failed update", async () => {
    mockFetch({
      users: [USER_A],
      onRequest: (method, url) => {
        if (method === "PUT" && url.includes(`/api/pam/users/${USER_A.id}/permissions`)) {
          return { ok: false, status: 500, json: async () => ({ detail: "fail" }) };
        }
        return undefined;
      },
    });
    renderPanel();

    await waitFor(() => expect(screen.getByText("operator1")).toBeInTheDocument());
    const assetsCheckbox = screen.getByRole("checkbox", {
      name: `operator1 — ${tr.pam.permissionAssetsView}`,
    }) as HTMLInputElement;
    fireEvent.click(assetsCheckbox);

    await waitFor(() => expect(assetsCheckbox.checked).toBe(false));
  });
});
