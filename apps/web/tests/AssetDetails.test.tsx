import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssetDetails } from "@/components/AssetDetails";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import type { Asset } from "@/lib/api";

const ASSET: Asset = {
  id: "11111111-1111-1111-1111-111111111111",
  ip_address: "10.0.5.1",
  hostname: "firewall.example.local",
  mac_address: "AA-BB-CC-DD-EE-FF",
  vendor: "Fortinet, Inc.",
  device_type: "firewall",
  confidence: "high",
  evidence: ["vendor: Fortinet", "port: 443 open"],
  open_ports: [{ port: 443, status: "open", latency_ms: 2.4 }],
  status: "up",
  latency_ms: 2.1,
  last_seen: "2026-08-26T10:00:00Z",
  created_at: "2026-08-26T09:00:00Z",
  updated_at: "2026-08-26T10:00:00Z",
};

const NULL_ASSET: Asset = {
  id: "22222222-2222-2222-2222-222222222222",
  ip_address: "10.0.5.2",
  hostname: null,
  mac_address: null,
  vendor: null,
  device_type: "unknown",
  confidence: "low",
  evidence: [],
  open_ports: [],
  status: "down",
  latency_ms: null,
  last_seen: "2026-08-26T08:00:00Z",
  created_at: "2026-08-26T07:00:00Z",
  updated_at: "2026-08-26T08:00:00Z",
};

function renderAssetDetails(asset: Asset, onClose: () => void) {
  return render(
    <LocaleProvider>
      <AssetDetails asset={asset} onClose={onClose} />
    </LocaleProvider>,
  );
}

function openTab(name: string) {
  fireEvent.click(screen.getByRole("tab", { name }));
}

const d = tr.assetDetails;

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AssetDetails", () => {
  it("shows overview fields by default", () => {
    renderAssetDetails(ASSET, vi.fn());

    expect(screen.getAllByText("firewall.example.local").length).toBeGreaterThan(0);
    expect(screen.getByText("10.0.5.1")).toBeInTheDocument();
    expect(screen.getByText(tr.deviceType.firewall)).toBeInTheDocument();
    expect(screen.getByText(`🟢 ${tr.status.up}`)).toBeInTheDocument();
    expect(screen.getByText(tr.confidence.high)).toBeInTheDocument();
  });

  it("shows network fields on the Network tab", () => {
    renderAssetDetails(ASSET, vi.fn());

    openTab(d.tabs.network);

    expect(screen.getByText("AA-BB-CC-DD-EE-FF")).toBeInTheDocument();
    expect(screen.getByText("Fortinet, Inc.")).toBeInTheDocument();
    expect(screen.getByText("2.1ms")).toBeInTheDocument();
  });

  it("shows discovery evidence on the Discovery tab", () => {
    renderAssetDetails(ASSET, vi.fn());

    openTab(d.tabs.discovery);

    expect(screen.getByText("vendor: Fortinet")).toBeInTheDocument();
    expect(screen.getByText("port: 443 open")).toBeInTheDocument();
  });

  it("shows a port with its risk badge on the Ports tab", () => {
    renderAssetDetails(ASSET, vi.fn());

    openTab(d.tabs.ports);

    expect(screen.getByText("443")).toBeInTheDocument();
    expect(screen.getByText(tr.risk.low)).toBeInTheDocument();
  });

  it("shows explicit no-data text on the Monitoring tab, never fabricated values", () => {
    renderAssetDetails(ASSET, vi.fn());

    openTab(d.tabs.monitoring);

    expect(screen.getByText(d.monitoring.notMonitored)).toBeInTheDocument();
    const noDataItems = screen.getAllByText(d.monitoring.noDataAvailable);
    expect(noDataItems.length).toBe(4); // CPU, Memory, Uptime, Temperature
    expect(screen.getByText(d.monitoring.noInterfaceData)).toBeInTheDocument();
  });

  it("shows '-' for null fields across tabs", () => {
    renderAssetDetails(NULL_ASSET, vi.fn());

    expect(screen.getByText("-")).toBeInTheDocument(); // Overview hostname

    openTab(d.tabs.network);
    expect(screen.getAllByText("-").length).toBeGreaterThan(0); // mac, vendor, latency

    openTab(d.tabs.discovery);
    expect(screen.getByText("-")).toBeInTheDocument(); // evidence

    openTab(d.tabs.ports);
    expect(screen.getByText(d.ports.noOpenPorts)).toBeInTheDocument();
  });

  it("calls onClose when the close button is clicked", () => {
    const onClose = vi.fn();
    renderAssetDetails(ASSET, onClose);

    fireEvent.click(screen.getByRole("button", { name: d.closeButton }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the backdrop is clicked", () => {
    const onClose = vi.fn();
    renderAssetDetails(ASSET, onClose);

    fireEvent.click(screen.getByLabelText(d.ariaLabel).parentElement as HTMLElement);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not call onClose when the panel itself is clicked", () => {
    const onClose = vi.fn();
    renderAssetDetails(ASSET, onClose);

    fireEvent.click(screen.getByLabelText(d.ariaLabel));

    expect(onClose).not.toHaveBeenCalled();
  });

  it("calls onClose when Escape is pressed", () => {
    const onClose = vi.fn();
    renderAssetDetails(ASSET, onClose);

    fireEvent.keyDown(window, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows a no-active-alerts message on the Alerts tab for a healthy device", () => {
    renderAssetDetails(ASSET, vi.fn());

    openTab(d.tabs.alerts);

    expect(screen.getByText(d.alerts.noAlertsForDevice)).toBeInTheDocument();
  });

  it("shows a real device_down alert on the Alerts tab, scoped to this device only", () => {
    renderAssetDetails(NULL_ASSET, vi.fn());

    openTab(d.tabs.alerts);

    expect(screen.getByText(tr.severity.critical)).toBeInTheDocument();
    expect(screen.getByText(/yanıt vermiyor/)).toBeInTheDocument();
  });

  it("links to the Topology page filtered to this device's IP", () => {
    renderAssetDetails(ASSET, vi.fn());

    expect(
      screen.getByRole("link", { name: new RegExp(tr.common.viewInTopology) }),
    ).toHaveAttribute("href", "/topology?ip=10.0.5.1");
  });

  it("shows 'Not configured' on the SNMP tab for an unconfigured asset", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ configured: false, profile: null }),
      }),
    );
    renderAssetDetails(ASSET, vi.fn());

    openTab(d.tabs.snmp);

    expect(await screen.findByText(d.snmp.notConfigured)).toBeInTheDocument();
    expect(screen.getByText(d.snmp.configureButton)).toBeInTheDocument();
  });

  it("shows the assigned profile's details on the SNMP tab", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          configured: true,
          target_host_matches_asset: true,
          profile: {
            id: "p1",
            name: "Core Switch SNMP",
            target_host: "10.0.5.1",
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
          },
        }),
      }),
    );
    renderAssetDetails(ASSET, vi.fn());

    openTab(d.tabs.snmp);

    expect(await screen.findByText("Core Switch SNMP")).toBeInTheDocument();
    expect(screen.getByText(tr.assets.snmpConfigured)).toBeInTheDocument();
    expect(screen.getByText(d.snmp.unassignButton)).toBeInTheDocument();
    expect(screen.queryByText(d.snmp.targetMismatchWarning)).not.toBeInTheDocument();
  });

  it("warns when the profile's own target differs from the asset's IP", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          configured: true,
          target_host_matches_asset: false,
          profile: {
            id: "p1",
            name: "Shared Profile",
            target_host: "10.0.9.9",
            port: 161,
            version: "v2c",
            timeout_seconds: 2,
            retries: 2,
            enabled: true,
            credential_configured: true,
            status: "ready",
            assigned_asset_count: 2,
            security_level: null,
            community_ref: "SNMP_SHARED_COMMUNITY",
            username: null,
            auth_protocol: null,
            auth_credential_ref: null,
            priv_protocol: null,
            priv_credential_ref: null,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        }),
      }),
    );
    renderAssetDetails(ASSET, vi.fn());

    openTab(d.tabs.snmp);

    expect(await screen.findByText(d.snmp.targetMismatchWarning)).toBeInTheDocument();
  });

  it("never renders a secret VALUE on the SNMP tab", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          configured: true,
          target_host_matches_asset: true,
          profile: {
            id: "p1",
            name: "Core Switch SNMP",
            target_host: "10.0.5.1",
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
          },
        }),
      }),
    );
    renderAssetDetails(ASSET, vi.fn());

    openTab(d.tabs.snmp);

    await waitFor(() => expect(screen.getByText("Core Switch SNMP")).toBeInTheDocument());
    expect(screen.queryByText(/gercek-|actual-secret/i)).not.toBeInTheDocument();
  });
});
