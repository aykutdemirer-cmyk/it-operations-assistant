import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VCenterPanel } from "@/components/vcenter/VCenterPanel";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { tr } from "@/lib/i18n/translations";
import { mockCurrentUser, setLoggedInToken } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const SUMMARY = {
  total_hosts: 1,
  total_vms: 1,
  powered_on_vms: 1,
  total_vcpu_allocated: 2,
  total_memory_gb_allocated: 4,
  datastores: [{ id: "ds-1", name: "datastore1", type: "VMFS", capacity_gb: 500, free_gb: 120 }],
};

const VMS = [
  { id: "vm-1", name: "web-01", power_state: "POWERED_ON", cpu_count: 2, memory_mb: 4096, ip_address: "10.0.1.5", guest_os: "ubuntu64Guest" },
  { id: "vm-2", name: "vCLS-a1b2c3", power_state: "POWERED_ON", cpu_count: 1, memory_mb: 128, ip_address: null, guest_os: "otherGuest" },
];

const VM_DETAIL = {
  ...VMS[0],
  guest_hostname: "web-01.lab.local",
  cpu_usage_percent: null,
  memory_usage_percent: null,
};

function mockFetch(handlers: {
  permissions?: string[];
  summaryStatus?: number;
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
        return { ok: true, json: async () => mockCurrentUser((handlers.permissions ?? ["VCENTER_VIEW"]) as never[], { role: "OPERATOR" }) };
      }
      if (handlers.onRequest) {
        const custom = handlers.onRequest(method, url, body);
        if (custom !== undefined) return custom;
      }
      if (url.endsWith("/api/vcenter/summary")) {
        if (handlers.summaryStatus === 409) {
          return { ok: false, status: 409, json: async () => ({ detail: "vCenter henüz yapılandırılmadı" }) };
        }
        return { ok: true, json: async () => SUMMARY };
      }
      if (url.endsWith("/api/vcenter/vms")) {
        return { ok: true, json: async () => VMS };
      }
      if (url.endsWith("/api/vcenter/vms/vm-1")) {
        return { ok: true, json: async () => VM_DETAIL };
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
        <VCenterPanel />
      </AuthProvider>
    </LocaleProvider>,
  );
}

describe("VCenterPanel", () => {
  it("shows an honest 'not configured' state instead of trying to connect", async () => {
    mockFetch({ summaryStatus: 409 });
    renderPanel();

    await waitFor(() => expect(screen.getByText(tr.vcenter.notConfiguredNoAccess)).toBeInTheDocument());
  });

  it("renders summary KPIs and the VM list from real data", async () => {
    mockFetch({});
    renderPanel();

    await waitFor(() => expect(screen.getByText("web-01")).toBeInTheDocument());
    expect(screen.getByText(tr.vcenter.kpi.totalVms)).toBeInTheDocument();
    expect(screen.getByText("10.0.1.5")).toBeInTheDocument();
    expect(screen.getByText("datastore1")).toBeInTheDocument();
  });

  it("opens VM detail and shows the honest 'not available' usage note — never a fabricated percentage", async () => {
    mockFetch({});
    renderPanel();
    await waitFor(() => expect(screen.getByText("web-01")).toBeInTheDocument());

    fireEvent.click(screen.getByText("web-01"));

    await waitFor(() => expect(screen.getByText("web-01.lab.local")).toBeInTheDocument());
    expect(screen.getAllByText(tr.vcenter.usageNotAvailable).length).toBeGreaterThan(0);
  });

  it("hides power action buttons for a user with VCENTER_VIEW but not VCENTER_ADMIN", async () => {
    mockFetch({ permissions: ["VCENTER_VIEW"] });
    renderPanel();
    await waitFor(() => expect(screen.getByText("web-01")).toBeInTheDocument());

    fireEvent.click(screen.getByText("web-01"));

    await waitFor(() => expect(screen.getByText("web-01.lab.local")).toBeInTheDocument());
    expect(screen.queryByText(tr.vcenter.powerStop)).not.toBeInTheDocument();
    // Görüntüleme yalnızca izniyle de bilet açma her zaman mümkün.
    expect(screen.getByText(tr.vcenter.openTicket)).toBeInTheDocument();
  });

  it("shows power action buttons and calls the power API for VCENTER_ADMIN", async () => {
    const calls = mockFetch({
      permissions: ["VCENTER_VIEW", "VCENTER_ADMIN"],
      onRequest: (method, url) => {
        if (url.endsWith("/api/vcenter/vms/vm-1/power") && method === "POST") {
          return { ok: true, json: async () => ({ status: "ok" }) };
        }
        return undefined;
      },
    });
    renderPanel();
    await waitFor(() => expect(screen.getByText("web-01")).toBeInTheDocument());

    fireEvent.click(screen.getByText("web-01"));
    await waitFor(() => expect(screen.getByRole("button", { name: tr.vcenter.powerStop })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: tr.vcenter.powerStop }));

    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/api/vcenter/vms/vm-1/power"))).toBe(true),
    );
  });

  it("hides vCLS system VMs by default and shows them under the System VMs toggle", async () => {
    mockFetch({});
    renderPanel();

    await waitFor(() => expect(screen.getByText("web-01")).toBeInTheDocument());
    expect(screen.queryByText("vCLS-a1b2c3")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText(`${tr.vcenter.systemVms} (1)`));

    expect(screen.getByText("vCLS-a1b2c3")).toBeInTheDocument();
    expect(screen.queryByText("web-01")).not.toBeInTheDocument();
  });

  it("opens the ticket modal prefilled from the table row action column", async () => {
    mockFetch({});
    renderPanel();
    await waitFor(() => expect(screen.getByText("web-01")).toBeInTheDocument());

    fireEvent.click(screen.getAllByText("🎫")[0]);

    const titleInput = await screen.findByDisplayValue(tr.vcenter.ticketPrefillTitle("web-01"));
    expect(titleInput).toBeInTheDocument();
  });

  it("triggers a power action directly from the table row dropdown for VCENTER_ADMIN", async () => {
    const calls = mockFetch({
      permissions: ["VCENTER_VIEW", "VCENTER_ADMIN"],
      onRequest: (method, url) => {
        if (url.endsWith("/api/vcenter/vms/vm-1/power") && method === "POST") {
          return { ok: true, json: async () => ({ status: "ok" }) };
        }
        return undefined;
      },
    });
    renderPanel();
    await waitFor(() => expect(screen.getByText("web-01")).toBeInTheDocument());

    fireEvent.change(screen.getByRole("combobox", { name: `${tr.vcenter.powerMenuLabel}: web-01` }), {
      target: { value: "guest_reboot" },
    });

    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.body && (c.body as { action: string }).action === "guest_reboot")).toBe(
        true,
      ),
    );
  });
});
