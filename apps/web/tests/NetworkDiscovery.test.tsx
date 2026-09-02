import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NetworkDiscovery } from "@/components/NetworkDiscovery";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderDiscovery() {
  return render(
    <LocaleProvider>
      <NetworkDiscovery />
    </LocaleProvider>,
  );
}

function typeCidr(value: string) {
  fireEvent.change(screen.getByLabelText(tr.discovery.cidrLabel), {
    target: { value },
  });
}

describe("NetworkDiscovery", () => {
  it("renders a CIDR input", () => {
    renderDiscovery();

    expect(screen.getByLabelText(tr.discovery.cidrLabel)).toBeInTheDocument();
  });

  it("sends the entered CIDR when Scan Network is clicked", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        cidr: "10.0.5.0/30",
        total_hosts: 2,
        alive_hosts: 1,
        hosts: [
          {
            ip: "10.0.5.1",
            status: "up",
            latency_ms: 2.1,
            mac_address: null,
            vendor: null,
            hostname: null,
            open_ports: [],
            device_type: "unknown",
            confidence: "low",
            evidence: [],
          },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    renderDiscovery();
    typeCidr("10.0.5.0/30");
    fireEvent.click(screen.getByRole("button", { name: tr.discovery.scanButton }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/discovery/icmp");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ cidr: "10.0.5.0/30" });
  });

  it("shows a scanning indicator while the request is in flight", async () => {
    let resolveFetch: (value: unknown) => void = () => {};
    const pending = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockReturnValue(pending),
    );

    renderDiscovery();
    typeCidr("10.0.5.0/30");
    fireEvent.click(screen.getByRole("button", { name: tr.discovery.scanButton }));

    expect(await screen.findByText(tr.discovery.scanning)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: tr.discovery.scanButton }),
    ).toBeDisabled();

    resolveFetch({
      ok: true,
      json: async () => ({
        cidr: "10.0.5.0/30",
        total_hosts: 2,
        alive_hosts: 0,
        hosts: [],
      }),
    });

    await waitFor(() =>
      expect(screen.queryByText(tr.discovery.scanning)).not.toBeInTheDocument(),
    );
  });

  it("renders the result table with hostname, MAC address, vendor, device type, confidence, open ports, status and latency", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          cidr: "10.0.5.0/30",
          total_hosts: 2,
          alive_hosts: 1,
          hosts: [
            {
              ip: "10.0.5.1",
              status: "up",
              latency_ms: 2.1,
              mac_address: "AA-BB-CC-DD-EE-FF",
              vendor: "Fortinet, Inc.",
              hostname: "firewall.example.local",
              open_ports: [
                { port: 22, status: "open", latency_ms: 2.0 },
                { port: 443, status: "open", latency_ms: 2.4 },
              ],
              device_type: "firewall",
              confidence: "high",
              evidence: ["vendor: Fortinet"],
            },
            {
              ip: "10.0.5.2",
              status: "down",
              latency_ms: null,
              mac_address: null,
              vendor: null,
              hostname: null,
              open_ports: [],
              device_type: "unknown",
              confidence: "low",
              evidence: [],
            },
          ],
        }),
      }),
    );

    renderDiscovery();
    typeCidr("10.0.5.0/30");
    fireEvent.click(screen.getByRole("button", { name: tr.discovery.scanButton }));

    await screen.findByText("10.0.5.1");
    const upRow = screen.getByText("10.0.5.1").closest("tr");
    expect(upRow).not.toBeNull();
    expect(within(upRow as HTMLElement).getByText("firewall.example.local")).toBeInTheDocument();
    expect(within(upRow as HTMLElement).getByText("AA-BB-CC-DD-EE-FF")).toBeInTheDocument();
    expect(within(upRow as HTMLElement).getByText("Fortinet, Inc.")).toBeInTheDocument();
    expect(
      within(upRow as HTMLElement).getByText(tr.deviceType.firewall),
    ).toBeInTheDocument();
    expect(within(upRow as HTMLElement).getByText(tr.confidence.high)).toBeInTheDocument();
    expect(within(upRow as HTMLElement).getByText("22, 443")).toBeInTheDocument();
    expect(
      within(upRow as HTMLElement).getByText(`🟢 ${tr.status.up}`),
    ).toBeInTheDocument();
    expect(within(upRow as HTMLElement).getByText("2.1ms")).toBeInTheDocument();

    const downRow = screen.getByText("10.0.5.2").closest("tr");
    expect(downRow).not.toBeNull();
    expect(
      within(downRow as HTMLElement).getByText(tr.deviceType.unknown),
    ).toBeInTheDocument();
    expect(within(downRow as HTMLElement).getByText(tr.confidence.low)).toBeInTheDocument();
    expect(
      within(downRow as HTMLElement).getByText(`🔴 ${tr.status.down}`),
    ).toBeInTheDocument();
    const downCells = within(downRow as HTMLElement).getAllByText("-");
    expect(downCells).toHaveLength(5); // hostname, MAC, vendor, open ports ve latency beşi de "-"
  });

  it("shows a summary of discovered hosts and open ports after a scan", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          cidr: "10.0.5.0/30",
          total_hosts: 2,
          alive_hosts: 1,
          hosts: [
            {
              ip: "10.0.5.1",
              status: "up",
              latency_ms: 1.0,
              mac_address: null,
              vendor: null,
              hostname: null,
              open_ports: [
                { port: 22, status: "open", latency_ms: 1.0 },
                { port: 443, status: "open", latency_ms: 1.2 },
              ],
              device_type: "unknown",
              confidence: "low",
              evidence: [],
            },
          ],
        }),
      }),
    );

    renderDiscovery();
    typeCidr("10.0.5.0/30");
    fireEvent.click(screen.getByRole("button", { name: tr.discovery.scanButton }));

    expect(
      await screen.findByText(
        `1 ${tr.discovery.hostsDiscovered} · 2 ${tr.discovery.openPortsFound}`,
      ),
    ).toBeInTheDocument();
  });

  it("shows an error message when the scan request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: async () => ({ detail: "Geçersiz CIDR" }),
      }),
    );

    renderDiscovery();
    typeCidr("not-a-cidr");
    fireEvent.click(screen.getByRole("button", { name: tr.discovery.scanButton }));

    expect(await screen.findByText("Geçersiz CIDR")).toBeInTheDocument();
  });
});
