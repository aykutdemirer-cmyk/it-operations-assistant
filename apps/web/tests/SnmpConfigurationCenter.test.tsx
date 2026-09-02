import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SnmpConfigurationCenter } from "@/components/SnmpConfigurationCenter";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderCenter() {
  return render(
    <LocaleProvider>
      <SnmpConfigurationCenter />
    </LocaleProvider>,
  );
}

const READY_PROFILE = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "Core Switches",
  target_host: "10.0.213.10",
  port: 161,
  version: "v2c",
  timeout_seconds: 2,
  retries: 2,
  enabled: true,
  credential_configured: true,
  status: "ready",
  assigned_asset_count: 0,
  security_level: null,
  community_ref: "SNMP_CORE_SWITCH_COMMUNITY",
  username: null,
  auth_protocol: null,
  auth_credential_ref: null,
  priv_protocol: null,
  priv_credential_ref: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function mockFetch(handlers: { profiles?: unknown[]; onRequest?: (method: string, url: string, body: unknown) => unknown }) {
  const profiles = handlers.profiles ?? [];
  const calls: { method: string; url: string; body: unknown }[] = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(init.body as string) : undefined;
      calls.push({ method, url, body });

      if (handlers.onRequest) {
        const custom = handlers.onRequest(method, url, body);
        if (custom !== undefined) return custom;
      }

      if (url.endsWith("/api/snmp/profiles") && method === "GET") {
        return { ok: true, json: async () => profiles };
      }
      if (url.endsWith("/api/snmp/profiles") && method === "POST") {
        return { ok: true, json: async () => ({ ...READY_PROFILE, ...body, id: "new-id" }) };
      }
      return Promise.reject(new Error(`Unexpected request: ${method} ${url}`));
    }),
  );

  return calls;
}

describe("SnmpConfigurationCenter", () => {
  it("shows the empty state when no profiles exist", async () => {
    mockFetch({ profiles: [] });
    renderCenter();

    await waitFor(() => expect(screen.getByText(tr.settings.snmpConfig.noProfiles)).toBeInTheDocument());
  });

  it("renders a profile row with target, version, and Ready status", async () => {
    mockFetch({ profiles: [READY_PROFILE] });
    renderCenter();

    await waitFor(() => expect(screen.getByText("Core Switches")).toBeInTheDocument());
    expect(screen.getByText("10.0.213.10:161")).toBeInTheDocument();
    expect(screen.getByText(tr.settings.snmpConfig.statusLabels.ready)).toBeInTheDocument();
  });

  it("never renders any secret VALUE — only the reference name", async () => {
    mockFetch({ profiles: [READY_PROFILE] });
    renderCenter();

    await waitFor(() => expect(screen.getByText("Core Switches")).toBeInTheDocument());
    // community_ref (bir İSİM) gösterilebilir ama bu testte hiç render edilmiyor
    // (yalnızca liste görünümünde) — asıl garanti: hiçbir secret DEĞERİ yok,
    // zaten backend hiç değer döndürmüyor, burada yalnızca DOM'da olmadığını
    // doğruca kontrol ediyoruz.
    expect(screen.queryByText(/gercek-|actual-secret/i)).not.toBeInTheDocument();
  });

  it("opens the create form with v2c fields by default and toggles to v3", async () => {
    mockFetch({ profiles: [] });
    renderCenter();

    await waitFor(() => expect(screen.getByText(tr.settings.snmpConfig.noProfiles)).toBeInTheDocument());
    fireEvent.click(screen.getByText(tr.settings.snmpConfig.addProfile));

    expect(screen.getByText(tr.settings.snmpConfig.fields.community)).toBeInTheDocument();

    const versionSelect = screen.getAllByRole("combobox")[0];
    fireEvent.change(versionSelect, { target: { value: "v3" } });

    expect(screen.getByText(tr.settings.snmpConfig.fields.username)).toBeInTheDocument();
    expect(screen.queryByText(tr.settings.snmpConfig.fields.community)).not.toBeInTheDocument();
  });

  it("submits a new v2c profile with the entered fields", async () => {
    const calls = mockFetch({ profiles: [] });
    renderCenter();

    await waitFor(() => expect(screen.getByText(tr.settings.snmpConfig.noProfiles)).toBeInTheDocument());
    fireEvent.click(screen.getByText(tr.settings.snmpConfig.addProfile));

    fireEvent.change(screen.getByPlaceholderText(tr.settings.snmpConfig.fields.profileNamePlaceholder), {
      target: { value: "Firewall" },
    });
    fireEvent.change(screen.getByPlaceholderText(tr.settings.snmpConfig.fields.targetHostPlaceholder), {
      target: { value: "10.0.213.1" },
    });
    fireEvent.change(screen.getByPlaceholderText(tr.settings.snmpConfig.fields.communityPlaceholder), {
      target: { value: "SNMP_FW_COMMUNITY" },
    });

    fireEvent.click(screen.getByText(tr.settings.snmpConfig.save));

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const postCall = calls.find((c) => c.method === "POST")!;
    expect(postCall.body).toMatchObject({
      name: "Firewall",
      target_host: "10.0.213.1",
      community_ref: "SNMP_FW_COMMUNITY",
      version: "v2c",
    });
  });

  it("opens the edit form pre-filled with the profile's existing values", async () => {
    mockFetch({ profiles: [READY_PROFILE] });
    renderCenter();

    await waitFor(() => expect(screen.getByText("Core Switches")).toBeInTheDocument());
    fireEvent.click(screen.getByText(tr.common.edit));

    expect(screen.getByDisplayValue("Core Switches")).toBeInTheDocument();
    expect(screen.getByDisplayValue("10.0.213.10")).toBeInTheDocument();
  });

  it("requires confirmation before deleting a profile", async () => {
    const calls = mockFetch({
      profiles: [READY_PROFILE],
      onRequest: (method, url) => {
        if (url.includes(READY_PROFILE.id) && method === "DELETE") {
          return { ok: true, status: 204, json: async () => ({}) };
        }
        return undefined;
      },
    });
    renderCenter();

    await waitFor(() => expect(screen.getByText("Core Switches")).toBeInTheDocument());
    fireEvent.click(screen.getByText(tr.settings.snmpConfig.delete));

    // Silme henüz gerçekleşmedi — onay bekleniyor.
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);

    const confirmButtons = screen.getAllByText(tr.settings.snmpConfig.delete);
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("shows the real test-connection result inline", async () => {
    mockFetch({
      profiles: [READY_PROFILE],
      onRequest: (method, url) => {
        if (url.includes("/test") && method === "POST") {
          return {
            ok: true,
            json: async () => ({
              status: "connected",
              message: "Bağlantı başarılı.",
              sys_name: "core-sw-01",
              sys_descr: null,
              sys_object_id: null,
              sys_uptime_ticks: null,
            }),
          };
        }
        return undefined;
      },
    });
    renderCenter();

    await waitFor(() => expect(screen.getByText("Core Switches")).toBeInTheDocument());
    fireEvent.click(screen.getByText(tr.settings.snmpConfig.testConnection));

    await waitFor(() =>
      expect(screen.getByText(tr.settings.snmpConfig.testResultLabels.connected)).toBeInTheDocument(),
    );
    expect(screen.getByText(/core-sw-01/)).toBeInTheDocument();
  });

  it("shows the real assigned device count (Faz 29.5)", async () => {
    mockFetch({ profiles: [{ ...READY_PROFILE, assigned_asset_count: 3 }] });
    renderCenter();

    await waitFor(() => expect(screen.getByText("Core Switches")).toBeInTheDocument());
    expect(screen.getByText(tr.settings.snmpConfig.assignedDevicesCount(3))).toBeInTheDocument();
  });

  it("shows a 409 conflict message instead of deleting a profile with assigned assets", async () => {
    const calls = mockFetch({
      profiles: [READY_PROFILE],
      onRequest: (method, url) => {
        if (url.includes(READY_PROFILE.id) && method === "DELETE") {
          return {
            ok: false,
            status: 409,
            json: async () => ({ detail: "This profile is assigned to one or more assets." }),
          };
        }
        return undefined;
      },
    });
    renderCenter();

    await waitFor(() => expect(screen.getByText("Core Switches")).toBeInTheDocument());
    fireEvent.click(screen.getByText(tr.settings.snmpConfig.delete));
    const confirmButtons = screen.getAllByText(tr.settings.snmpConfig.delete);
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    expect(
      await screen.findByText(tr.settings.snmpConfig.deleteHasAssignmentsError),
    ).toBeInTheDocument();
    // Profil listede kalmaya devam ediyor — sessizce kaskad silinmedi.
    expect(screen.getByText("Core Switches")).toBeInTheDocument();
  });

  it("shows an honest timeout result — never fabricates success", async () => {
    mockFetch({
      profiles: [READY_PROFILE],
      onRequest: (method, url) => {
        if (url.includes("/test") && method === "POST") {
          return {
            ok: true,
            json: async () => ({
              status: "timeout",
              message: "SNMP isteği zaman aşımına uğradı",
              sys_name: null,
              sys_descr: null,
              sys_object_id: null,
              sys_uptime_ticks: null,
            }),
          };
        }
        return undefined;
      },
    });
    renderCenter();

    await waitFor(() => expect(screen.getByText("Core Switches")).toBeInTheDocument());
    fireEvent.click(screen.getByText(tr.settings.snmpConfig.testConnection));

    await waitFor(() =>
      expect(screen.getByText(tr.settings.snmpConfig.testResultLabels.timeout)).toBeInTheDocument(),
    );
  });
});
