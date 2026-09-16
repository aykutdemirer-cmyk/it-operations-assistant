import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PamTagsPanel } from "@/components/PamTagsPanel";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const TAG_PRODUCTION = { id: "t1", name: "Production", created_at: new Date().toISOString() };
const ASSET = { id: "a1", ip_address: "10.0.9.10", hostname: "srv1.example.local" };

function mockFetch(handlers: {
  tags?: unknown[];
  assets?: unknown[];
  tagAssets?: unknown[];
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
      if (/\/api\/pam\/tags\/[^/]+\/assets/.test(url)) {
        return { ok: true, json: async () => handlers.tagAssets ?? [] };
      }
      if (url.includes("/api/pam/tags")) {
        return { ok: true, json: async () => handlers.tags ?? [] };
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
        <PamTagsPanel />
      </AuthProvider>
    </LocaleProvider>,
  );
}

describe("PamTagsPanel", () => {
  it("lists tags and creates a new one", async () => {
    const calls = mockFetch({
      tags: [TAG_PRODUCTION],
      onRequest: (method, url) => {
        if (method === "POST" && url.includes("/api/pam/tags")) {
          return { ok: true, json: async () => ({ id: "t2", name: "Linux", created_at: new Date().toISOString() }) };
        }
        return undefined;
      },
    });
    renderPanel();

    await waitFor(() => expect(screen.getByText("🏷️ Production")).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText(tr.pam.newTagPlaceholder), { target: { value: "Linux" } });
    fireEvent.click(screen.getByRole("button", { name: tr.pam.create }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.includes("/api/pam/tags"))).toBe(true));
  });

  it("opens the manage-assets modal and toggles a device assignment", async () => {
    const calls = mockFetch({ tags: [TAG_PRODUCTION], assets: [ASSET], tagAssets: [] });
    renderPanel();

    await waitFor(() => expect(screen.getByText("🏷️ Production")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: tr.pam.manageAssets }));

    await waitFor(() => expect(screen.getByText("srv1.example.local")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("checkbox"));

    await waitFor(() =>
      expect(calls.some((c) => c.method === "PUT" && c.url.includes(`/api/pam/tags/${TAG_PRODUCTION.id}/assets/${ASSET.id}`))).toBe(
        true,
      ),
    );
  });

  it("deletes a tag", async () => {
    const calls = mockFetch({
      tags: [TAG_PRODUCTION],
      onRequest: (method, url) => {
        if (method === "DELETE" && url.includes(`/api/pam/tags/${TAG_PRODUCTION.id}`)) {
          return { ok: true, status: 204, json: async () => null };
        }
        return undefined;
      },
    });
    renderPanel();

    await waitFor(() => expect(screen.getByText("🏷️ Production")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: tr.pam.delete }));

    await waitFor(() => expect(screen.getByRole("alertdialog")).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole("button", { name: tr.pam.delete }).slice(-1)[0]);

    await waitFor(() =>
      expect(calls.some((c) => c.method === "DELETE" && c.url.includes(`/api/pam/tags/${TAG_PRODUCTION.id}`))).toBe(true),
    );
  });
});
