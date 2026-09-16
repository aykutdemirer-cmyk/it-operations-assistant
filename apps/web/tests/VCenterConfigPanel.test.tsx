import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VCenterConfigPanel } from "@/components/vcenter/VCenterConfigPanel";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const CONFIGURED = {
  host: "vcenter.company.local",
  port: 443,
  username: "svc@vsphere.local",
  verify_ssl: false,
  last_test_status: null,
  last_test_error: null,
  last_test_at: null,
  updated_at: "2026-01-01T00:00:00Z",
};

function mockFetch(handlers: { config?: unknown; onRequest?: (method: string, url: string, body: unknown) => unknown }) {
  const calls: { method: string; url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(init.body as string) : undefined;
      calls.push({ method, url, body });

      if (url.includes("/api/auth/me")) {
        return { ok: true, json: async () => mockCurrentUser(["VCENTER_ADMIN"], { role: "ADMIN" }) };
      }
      if (handlers.onRequest) {
        const custom = handlers.onRequest(method, url, body);
        if (custom !== undefined) return custom;
      }
      if (url.endsWith("/api/settings/vcenter") && method === "GET") {
        return { ok: true, json: async () => handlers.config ?? null };
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
        <VCenterConfigPanel />
      </AuthProvider>
    </LocaleProvider>,
  );
}

describe("VCenterConfigPanel", () => {
  it("shows 'not configured' when no vCenter config exists yet", async () => {
    mockFetch({ config: null });
    renderPanel();
    await waitFor(() => expect(screen.getByText(tr.settings.vcenterConfig.notConfigured)).toBeInTheDocument());
  });

  it("submits the form as a PUT when saving", async () => {
    const calls = mockFetch({
      config: null,
      onRequest: (method, url, body) => {
        if (url.endsWith("/api/settings/vcenter") && method === "PUT") {
          return { ok: true, json: async () => ({ ...CONFIGURED, ...(body as Record<string, unknown>) }) };
        }
        return undefined;
      },
    });
    renderPanel();
    await waitFor(() => expect(screen.getByText(tr.settings.vcenterConfig.notConfigured)).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText(tr.settings.vcenterConfig.fields.hostPlaceholder), {
      target: { value: "vcenter.company.local" },
    });
    fireEvent.change(screen.getByPlaceholderText(tr.settings.vcenterConfig.fields.usernamePlaceholder), {
      target: { value: "svc@vsphere.local" },
    });
    fireEvent.change(screen.getByPlaceholderText(""), { target: { value: "s3cret" } });
    fireEvent.click(screen.getByRole("button", { name: tr.settings.vcenterConfig.save }));

    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({
      host: "vcenter.company.local",
      username: "svc@vsphere.local",
      password: "s3cret",
    });
  });

  it("never sends the saved password back — password field starts empty", async () => {
    mockFetch({ config: CONFIGURED });
    renderPanel();
    await waitFor(() => expect(screen.getByDisplayValue("vcenter.company.local")).toBeInTheDocument());

    const passwordInput = screen.getByPlaceholderText(tr.settings.vcenterConfig.fields.passwordKeepPlaceholder);
    expect(passwordInput).toHaveValue("");
  });

  it("shows a success toast on test connection", async () => {
    mockFetch({
      config: CONFIGURED,
      onRequest: (method, url) => {
        if (url.endsWith("/api/settings/vcenter/test") && method === "POST") {
          return { ok: true, json: async () => ({ success: true, message: "Bağlantı başarılı" }) };
        }
        return undefined;
      },
    });
    renderPanel();
    await waitFor(() => expect(screen.getByDisplayValue("vcenter.company.local")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: tr.settings.vcenterConfig.testConnection }));

    await waitFor(() => expect(screen.getByText(/Bağlantı başarılı/)).toBeInTheDocument());
  });
});
