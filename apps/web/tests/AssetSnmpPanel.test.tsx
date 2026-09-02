import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssetSnmpPanel } from "@/components/AssetSnmpPanel";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPanel(assetId = "asset-1") {
  return render(
    <LocaleProvider>
      <AssetSnmpPanel assetId={assetId} />
    </LocaleProvider>,
  );
}

const PROFILE = {
  id: "profile-1",
  name: "Core Switch SNMP",
  target_host: "10.0.213.1",
  port: 161,
  version: "v2c",
  timeout_seconds: 2,
  retries: 2,
  enabled: true,
  credential_configured: true,
  status: "ready",
  assigned_asset_count: 1,
  security_level: null,
  community_ref: "SNMP_CORE_COMMUNITY",
  username: null,
  auth_protocol: null,
  auth_credential_ref: null,
  priv_protocol: null,
  priv_credential_ref: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const d = tr.assetDetails.snmp;

function mockFetch(handlers: {
  assetProfile: unknown;
  profiles?: unknown[];
  onRequest?: (method: string, url: string) => unknown;
}) {
  const calls: { method: string; url: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url });

      if (handlers.onRequest) {
        const custom = handlers.onRequest(method, url);
        if (custom !== undefined) return custom;
      }
      if (url.includes("/snmp-profile") && method === "GET") {
        return { ok: true, json: async () => handlers.assetProfile };
      }
      if (url.endsWith("/api/snmp/profiles") && method === "GET") {
        return { ok: true, json: async () => handlers.profiles ?? [] };
      }
      return Promise.reject(new Error(`Unexpected request: ${method} ${url}`));
    }),
  );
  return calls;
}

describe("AssetSnmpPanel", () => {
  it("shows 'Not configured' and a Configure SNMP button when unassigned", async () => {
    mockFetch({ assetProfile: { configured: false, profile: null } });

    renderPanel();

    expect(await screen.findByText(d.notConfigured)).toBeInTheDocument();
    expect(screen.getByText(d.configureButton)).toBeInTheDocument();
    expect(screen.getByText(d.noPollDataAvailable)).toBeInTheDocument();
  });

  it("shows profile details and Poll Now when configured", async () => {
    mockFetch({
      assetProfile: { configured: true, profile: PROFILE, target_host_matches_asset: true },
    });

    renderPanel();

    expect(await screen.findByText("Core Switch SNMP")).toBeInTheDocument();
    expect(screen.getByText("v2c")).toBeInTheDocument();
    expect(screen.getByText(d.pollNowButton)).toBeInTheDocument();
    expect(screen.getByText(d.unassignButton)).toBeInTheDocument();
  });

  it("lets the user select and assign a profile", async () => {
    const calls = mockFetch({
      assetProfile: { configured: false, profile: null },
      profiles: [PROFILE],
      onRequest: (method, url) => {
        if (url.includes("/snmp-profile/") && method === "PUT") {
          return { ok: true, json: async () => ({ status: "assigned" }) };
        }
        return undefined;
      },
    });

    renderPanel();
    await screen.findByText(d.notConfigured);

    fireEvent.click(screen.getByText(d.configureButton));
    const select = await screen.findByRole("combobox");
    await waitFor(() => expect(screen.getByText(/Core Switch SNMP/)).toBeInTheDocument());
    fireEvent.change(select, { target: { value: "profile-1" } });
    fireEvent.click(screen.getByText(d.assignButton));

    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
  });

  it("unassigns the current profile", async () => {
    const calls = mockFetch({
      assetProfile: { configured: true, profile: PROFILE, target_host_matches_asset: true },
      onRequest: (method, url) => {
        if (url.includes("/snmp-profile") && method === "DELETE") {
          return { ok: true, json: async () => ({ status: "unassigned" }) };
        }
        return undefined;
      },
    });

    renderPanel();
    await screen.findByText("Core Switch SNMP");

    fireEvent.click(screen.getByText(d.unassignButton));

    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("polls now and shows the honest result — never fabricates success", async () => {
    mockFetch({
      assetProfile: { configured: true, profile: PROFILE, target_host_matches_asset: true },
      onRequest: (method, url) => {
        if (url.includes("/snmp/poll/") && method === "POST") {
          return {
            ok: true,
            json: async () => ({
              asset_id: "asset-1",
              polled_at: "2026-01-01T00:00:00Z",
              status: "unreachable",
              system: null,
              interfaces: [],
              error: "SNMP cihazı yanıt vermedi.",
              duration_ms: 1200,
            }),
          };
        }
        return undefined;
      },
    });

    renderPanel();
    await screen.findByText("Core Switch SNMP");

    fireEvent.click(screen.getByText(d.pollNowButton));

    await waitFor(() => expect(screen.getByText(/unreachable/)).toBeInTheDocument());
  });

  it("warns when the profile's own target host differs from the asset's IP", async () => {
    mockFetch({
      assetProfile: { configured: true, profile: PROFILE, target_host_matches_asset: false },
    });

    renderPanel();

    expect(await screen.findByText(d.targetMismatchWarning)).toBeInTheDocument();
  });
});
