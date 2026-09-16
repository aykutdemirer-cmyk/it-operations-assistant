import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LdapConfigurationCenter } from "@/components/LdapConfigurationCenter";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const CONFIGURED = {
  host: "dc01.lab.local",
  port: 389,
  use_ssl: false,
  domain_fqdn: "lab.local",
  base_dn: "DC=lab,DC=local",
  bind_dn: "svc-ldap-sync@lab.local",
  bind_password_masked: "••••••••",
  last_sync_status: null,
  last_sync_error: null,
  last_sync_at: null,
  updated_at: "2026-01-01T00:00:00Z",
};

function mockFetch(handlers: {
  config?: unknown;
  onRequest?: (method: string, url: string, body: unknown) => unknown;
}) {
  const calls: { method: string; url: string; body: unknown }[] = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(init.body as string) : undefined;
      calls.push({ method, url, body });

      if (url.includes("/api/auth/me")) {
        return { ok: true, json: async () => mockCurrentUser(["PAM_ADMIN"]) };
      }
      if (handlers.onRequest) {
        const custom = handlers.onRequest(method, url, body);
        if (custom !== undefined) return custom;
      }
      if (url.endsWith("/api/settings/ldap") && method === "GET") {
        return { ok: true, json: async () => handlers.config ?? null };
      }
      return Promise.reject(new Error(`Unexpected request: ${method} ${url}`));
    }),
  );

  return calls;
}

function renderCenter() {
  setLoggedInToken();
  return render(
    <LocaleProvider>
      <AuthProvider>
        <LdapConfigurationCenter />
      </AuthProvider>
    </LocaleProvider>,
  );
}

describe("LdapConfigurationCenter", () => {
  it("shows 'not configured' when no LDAP config exists yet", async () => {
    mockFetch({ config: null });
    renderCenter();

    await waitFor(() => expect(screen.getByText(tr.settings.ldapConfig.notConfigured)).toBeInTheDocument());
  });

  it("submits the form fields as a PUT request when saving", async () => {
    const calls = mockFetch({
      config: null,
      onRequest: (method, url, body) => {
        if (url.endsWith("/api/settings/ldap") && method === "PUT") {
          return { ok: true, json: async () => ({ ...CONFIGURED, ...(body as Record<string, unknown>) }) };
        }
        return undefined;
      },
    });
    renderCenter();

    await waitFor(() => expect(screen.getByText(tr.settings.ldapConfig.notConfigured)).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText(tr.settings.ldapConfig.fields.hostPlaceholder), {
      target: { value: "dc01.lab.local" },
    });
    fireEvent.change(screen.getByPlaceholderText(tr.settings.ldapConfig.fields.domainFqdnPlaceholder), {
      target: { value: "lab.local" },
    });
    fireEvent.change(screen.getByPlaceholderText(tr.settings.ldapConfig.fields.baseDnPlaceholder), {
      target: { value: "DC=lab,DC=local" },
    });
    fireEvent.change(screen.getByPlaceholderText(tr.settings.ldapConfig.fields.bindDnPlaceholder), {
      target: { value: "svc-ldap-sync@lab.local" },
    });
    fireEvent.change(screen.getByPlaceholderText(tr.settings.ldapConfig.fields.bindPasswordPlaceholder), {
      target: { value: "s3cret" },
    });

    fireEvent.click(screen.getByRole("button", { name: tr.settings.ldapConfig.save }));

    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const putCall = calls.find((c) => c.method === "PUT");
    expect(putCall?.body).toMatchObject({
      host: "dc01.lab.local",
      domain_fqdn: "lab.local",
      base_dn: "DC=lab,DC=local",
      bind_dn: "svc-ldap-sync@lab.local",
      bind_password: "s3cret",
    });
  });

  it("shows the last sync status once a config exists", async () => {
    mockFetch({ config: { ...CONFIGURED, last_sync_status: "success", last_sync_at: "2026-01-02T00:00:00Z" } });
    renderCenter();

    await waitFor(() =>
      expect(screen.getByText(new RegExp(tr.settings.ldapConfig.lastSyncStatusSuccess))).toBeInTheDocument(),
    );
  });
});
