import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SmtpConfigurationCenter } from "@/components/SmtpConfigurationCenter";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const CONFIGURED = {
  enabled: true,
  server: "smtp.company.local",
  port: 587,
  encryption: "tls",
  username: "notify@company.local",
  password_set: true,
  from_email: "notify@company.local",
  from_name: "IT Operations Helpdesk",
  it_group_email: "it@company.local",
  base_url: "https://itops.company.local",
  last_test_status: null,
  last_test_error: null,
  last_test_at: null,
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
        return { ok: true, json: async () => mockCurrentUser([], { role: "ADMIN" }) };
      }
      if (handlers.onRequest) {
        const custom = handlers.onRequest(method, url, body);
        if (custom !== undefined) return custom;
      }
      if (url.endsWith("/api/settings/smtp") && method === "GET") {
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
        <SmtpConfigurationCenter />
      </AuthProvider>
    </LocaleProvider>,
  );
}

describe("SmtpConfigurationCenter", () => {
  it("shows 'not configured' when no SMTP config exists yet", async () => {
    mockFetch({ config: null });
    renderCenter();
    await waitFor(() => expect(screen.getByText(tr.settings.smtpConfig.notConfigured)).toBeInTheDocument());
  });

  it("submits the form as a PUT when saving", async () => {
    const calls = mockFetch({
      config: null,
      onRequest: (method, url, body) => {
        if (url.endsWith("/api/settings/smtp") && method === "PUT") {
          return { ok: true, json: async () => ({ ...CONFIGURED, ...(body as Record<string, unknown>) }) };
        }
        return undefined;
      },
    });
    renderCenter();
    await waitFor(() => expect(screen.getByText(tr.settings.smtpConfig.notConfigured)).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText(tr.settings.smtpConfig.fields.serverPlaceholder), {
      target: { value: "smtp.company.local" },
    });
    fireEvent.change(screen.getByPlaceholderText(tr.settings.smtpConfig.fields.fromEmailPlaceholder), {
      target: { value: "notify@company.local" },
    });
    fireEvent.change(screen.getByPlaceholderText(tr.settings.smtpConfig.fields.passwordPlaceholder), {
      target: { value: "s3cret" },
    });
    fireEvent.change(screen.getByPlaceholderText(tr.settings.smtpConfig.fields.fromNamePlaceholder), {
      target: { value: "Helpdesk Team" },
    });
    fireEvent.click(screen.getByRole("button", { name: tr.settings.smtpConfig.save }));

    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({
      server: "smtp.company.local",
      from_email: "notify@company.local",
      from_name: "Helpdesk Team",
      password: "s3cret",
      encryption: "tls",
    });
  });

  it("suggests the typical port when the encryption type changes", async () => {
    mockFetch({ config: null });
    renderCenter();
    await waitFor(() => expect(screen.getByText(tr.settings.smtpConfig.notConfigured)).toBeInTheDocument());

    const portInput = screen.getByDisplayValue("587");
    fireEvent.change(screen.getByLabelText(tr.settings.smtpConfig.fields.encryption), { target: { value: "ssl" } });

    expect(portInput).toHaveValue(465);
  });

  it("sends a test email via POST /test", async () => {
    const calls = mockFetch({
      config: CONFIGURED,
      onRequest: (method, url) => {
        if (url.endsWith("/api/settings/smtp/test") && method === "POST") {
          return { ok: true, json: async () => ({ success: true, message: "ok" }) };
        }
        return undefined;
      },
    });
    renderCenter();
    await waitFor(() => expect(screen.getByPlaceholderText(tr.settings.smtpConfig.testToPlaceholder)).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText(tr.settings.smtpConfig.testToPlaceholder), {
      target: { value: "me@company.local" },
    });
    fireEvent.click(screen.getByRole("button", { name: tr.settings.smtpConfig.testButton }));

    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/api/settings/smtp/test") && c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/test"))?.body).toMatchObject({ to: "me@company.local" });
  });
});
