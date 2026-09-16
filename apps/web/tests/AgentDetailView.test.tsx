import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentDetailView } from "@/components/AgentDetailView";
import { tr } from "@/lib/i18n/translations";
import { renderWithDashboardData } from "./testUtils";

afterEach(() => {
  vi.restoreAllMocks();
});

const AGENT_ID = "11111111-1111-1111-1111-111111111111";

const BASE_AGENT_DETAIL = {
  id: AGENT_ID,
  hostname: "win-server-01",
  fqdn: "win-server-01.lab.local",
  os: "windows",
  os_version: "Windows Server 2022",
  agent_version: "1.0.0",
  asset_id: null,
  status: "online",
  registered_at: "2026-01-01T00:00:00Z",
  last_heartbeat_at: new Date().toISOString(),
  architecture: "AMD64",
  local_ip: "10.0.213.30",
  mac_address: "00-50-56-92-6D-A3",
  capabilities: ["heartbeat", "telemetry", "inventory"],
  revoked_at: null,
  latest_telemetry: null,
  inventory: null,
};

function mockAgentDetail(detail: unknown, status = 200, assets: unknown[] = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.includes(`/api/agents/${AGENT_ID}`)) {
        return Promise.resolve({ ok: status < 400, status, json: async () => detail });
      }
      if (url.includes("/api/assets")) {
        return Promise.resolve({ ok: true, json: async () => assets });
      }
      return Promise.resolve({ ok: true, json: async () => [] });
    }),
  );
}

// Faz 60 — PAM RDP/SSH butonları yalnızca agent GERÇEK bir cihaza
// bağlıysa (`agent.asset_id`) gösterilir; DashboardData'dan gelen
// `assets` listesinde eşleşen kayıt olmalı.
const LINKED_ASSET_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const LINKED_ASSET = { id: LINKED_ASSET_ID, hostname: "win-server-01.lab.local", ip_address: "10.0.213.30" };

describe("AgentDetailView", () => {
  it("shows overview fields for a real agent", async () => {
    mockAgentDetail(BASE_AGENT_DETAIL);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    expect(await screen.findByRole("heading", { name: "win-server-01" })).toBeInTheDocument();
    expect(screen.getByText("win-server-01.lab.local")).toBeInTheDocument();
    expect(screen.getByText(tr.agents.statusLabels.online)).toBeInTheDocument();
  });

  it("shows a not-found message for an unknown agent", async () => {
    mockAgentDetail({ detail: "Agent bulunamadı" }, 404);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    expect(await screen.findByText(tr.agentDetails.notFound)).toBeInTheDocument();
  });

  it("shows honest 'no telemetry data' on the CPU tab when nothing was polled yet", async () => {
    mockAgentDetail(BASE_AGENT_DETAIL);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.cpu }));

    expect(screen.getByText(tr.agentDetails.noTelemetryData)).toBeInTheDocument();
  });

  it("shows real CPU/memory telemetry when available — never fabricated", async () => {
    mockAgentDetail({
      ...BASE_AGENT_DETAIL,
      latest_telemetry: {
        collected_at: "2026-01-01T00:00:00Z",
        schema_version: 1,
        cpu_percent: 12.5,
        memory_total_bytes: 16_000_000_000,
        memory_used_bytes: 8_000_000_000,
        memory_percent: 50.0,
        disks: [],
        network_interfaces: [],
      },
    });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.cpu }));
    expect(screen.getByText("12.5%")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.memory }));
    expect(screen.getByText("50.0%")).toBeInTheDocument();
  });

  it("shows real process list on the Processes tab, never a command line", async () => {
    mockAgentDetail({
      ...BASE_AGENT_DETAIL,
      inventory: {
        collected_at: "2026-01-01T00:00:00Z",
        schema_version: 1,
        hardware: null,
        os: null,
        network_interfaces: [],
        software: [],
        services: [],
        processes: [
          { pid: 1234, name: "postgres.exe", cpu_percent: 1.2, memory_percent: 3.4, username: "SYSTEM", status: "running" },
        ],
      },
    });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.processes }));

    expect(screen.getByText("postgres.exe")).toBeInTheDocument();
    expect(screen.getByText("1234")).toBeInTheDocument();
    expect(screen.queryByText(/--password|cmdline/)).not.toBeInTheDocument();
  });

  const MULTI_PROCESS_AGENT = {
    ...BASE_AGENT_DETAIL,
    inventory: {
      collected_at: "2026-01-01T00:00:00Z",
      schema_version: 1,
      hardware: null,
      os: null,
      network_interfaces: [],
      software: [],
      services: [],
      processes: [
        { pid: 0, name: "System Idle Process", cpu_percent: 88.8, memory_percent: 0.0, username: "SYSTEM", status: "running" },
        { pid: 100, name: "low-cpu.exe", cpu_percent: 1.0, memory_percent: 1.0, username: "SYSTEM", status: "running" },
        { pid: 200, name: "high-cpu.exe", cpu_percent: 50.0, memory_percent: 2.0, username: "SYSTEM", status: "running" },
      ],
    },
  };

  it("sorts the process table by CPU % descending by default", async () => {
    mockAgentDetail(MULTI_PROCESS_AGENT);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.processes }));

    const rows = screen.getAllByRole("row").slice(1); // ilk satır header
    expect(within(rows[0] as HTMLElement).getByText(/System Idle/)).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).getByText("high-cpu.exe")).toBeInTheDocument();
    expect(within(rows[2] as HTMLElement).getByText("low-cpu.exe")).toBeInTheDocument();
  });

  it("labels PID 0 as idle instead of hiding it", async () => {
    mockAgentDetail(MULTI_PROCESS_AGENT);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.processes }));

    expect(screen.getByText((content) => content.includes(tr.agentDetails.processes.idle))).toBeInTheDocument();
  });

  it("toggles sort direction when clicking the same column header twice", async () => {
    mockAgentDetail(MULTI_PROCESS_AGENT);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.processes }));
    const cpuHeader = screen.getByRole("button", { name: new RegExp(tr.agentDetails.processes.cpu) });

    // Varsayılan zaten CPU % AZALAN — ilk tıklama ARTAN'a çevirir (en
    // düşük CPU üstte), ikinci tıklama tekrar AZALAN'a döner.
    fireEvent.click(cpuHeader);
    let rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0] as HTMLElement).getByText("low-cpu.exe")).toBeInTheDocument();

    fireEvent.click(cpuHeader);
    rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0] as HTMLElement).getByText(/System Idle/)).toBeInTheDocument();
  });

  it("filters the process table by search text", async () => {
    mockAgentDetail(MULTI_PROCESS_AGENT);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.processes }));
    fireEvent.change(screen.getByPlaceholderText(tr.agentDetails.processes.searchPlaceholder), {
      target: { value: "high-cpu" },
    });

    expect(screen.getByText("high-cpu.exe")).toBeInTheDocument();
    expect(screen.queryByText("low-cpu.exe")).not.toBeInTheDocument();
  });

  it("filters the process table by PID", async () => {
    mockAgentDetail(MULTI_PROCESS_AGENT);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.processes }));
    fireEvent.change(screen.getByPlaceholderText(tr.agentDetails.processes.searchPlaceholder), {
      target: { value: "200" },
    });

    expect(screen.getByText("high-cpu.exe")).toBeInTheDocument();
    expect(screen.queryByText("low-cpu.exe")).not.toBeInTheDocument();
  });

  it("shows honest 'no process data' when inventory has none", async () => {
    mockAgentDetail(BASE_AGENT_DETAIL);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.processes }));

    expect(screen.getByText(tr.agentDetails.processes.noData)).toBeInTheDocument();
  });

  // --- Faz 33: process kill / service control ---

  const AGENT_WITH_PROCESS_AND_SERVICE = {
    ...BASE_AGENT_DETAIL,
    inventory: {
      collected_at: "2026-01-01T00:00:00Z",
      schema_version: 1,
      hardware: null,
      os: null,
      network_interfaces: [],
      software: [],
      services: [{ name: "spooler", display_name: "Print Spooler", state: "running", startup_type: "auto" }],
      processes: [{ pid: 1234, name: "postgres.exe", cpu_percent: 1.2, memory_percent: 3.4, username: "SYSTEM", status: "running" }],
    },
  };

  function mockAgentDetailWithCommands(detail: unknown, commandOutcome: Record<string, unknown>) {
    let created: Record<string, unknown> | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (url.includes("/commands/") === false && url.endsWith("/commands") && init?.method === "POST") {
          created = { id: "cmd-1", status: "pending", result_detail: null, ...JSON.parse(String(init.body)) };
          return Promise.resolve({ ok: true, status: 201, json: async () => created });
        }
        if (url.endsWith("/commands")) {
          return Promise.resolve({ ok: true, status: 200, json: async () => [{ id: "cmd-1", ...commandOutcome }] });
        }
        if (url.includes(`/api/agents/${AGENT_ID}`) && !url.includes("/commands")) {
          return Promise.resolve({ ok: true, status: 200, json: async () => detail });
        }
        return Promise.resolve({ ok: true, json: async () => [] });
      }),
    );
  }

  it("shows a confirmation modal before killing a process", async () => {
    mockAgentDetailWithCommands(AGENT_WITH_PROCESS_AND_SERVICE, { status: "succeeded" });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.processes }));
    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.processes.kill }));

    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(screen.getByText(tr.agentCommands.confirmKillProcess("1234"))).toBeInTheDocument();
  });

  it("cancelling the modal does not submit a command", async () => {
    mockAgentDetailWithCommands(AGENT_WITH_PROCESS_AND_SERVICE, { status: "succeeded" });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.processes }));
    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.processes.kill }));
    fireEvent.click(screen.getByRole("button", { name: tr.agentCommands.cancelButton }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("confirming kill process shows a success toast", async () => {
    mockAgentDetailWithCommands(AGENT_WITH_PROCESS_AND_SERVICE, {
      status: "succeeded",
      result_detail: "PID 1234 sonlandırıldı",
    });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.processes }));
    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.processes.kill }));
    fireEvent.click(screen.getByRole("button", { name: tr.agentCommands.confirmButton }));

    expect(await screen.findByText(tr.agentCommands.successKill("1234"))).toBeInTheDocument();
  });

  it("confirming a failed command shows an error toast", async () => {
    mockAgentDetailWithCommands(AGENT_WITH_PROCESS_AND_SERVICE, {
      status: "failed",
      result_detail: "PID korumalı",
    });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.processes }));
    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.processes.kill }));
    fireEvent.click(screen.getByRole("button", { name: tr.agentCommands.confirmButton }));

    expect(await screen.findByText(tr.agentCommands.failure("PID korumalı"))).toBeInTheDocument();
  });

  it("shows Start/Stop/Restart buttons on the Services tab", async () => {
    mockAgentDetailWithCommands(AGENT_WITH_PROCESS_AND_SERVICE, { status: "succeeded" });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.services }));

    expect(screen.getByRole("button", { name: tr.agentDetails.services.start })).toBeDisabled();
    expect(screen.getByRole("button", { name: tr.agentDetails.services.stop })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: tr.agentDetails.services.restart })).not.toBeDisabled();
  });

  it("clicking Restart on a service opens a confirmation modal", async () => {
    mockAgentDetailWithCommands(AGENT_WITH_PROCESS_AND_SERVICE, { status: "succeeded" });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.services }));
    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.services.restart }));

    expect(
      screen.getByText(tr.agentCommands.confirmServiceControl("Print Spooler", tr.agentCommands.actionRestart)),
    ).toBeInTheDocument();
  });

  // --- Faz 33.1: manual "Yenile" (refresh) button ---

  it("clicking Yenile submits a refresh_inventory command without a confirmation modal", async () => {
    let refreshBody: Record<string, unknown> | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (url.endsWith("/commands") && init?.method === "POST") {
          refreshBody = JSON.parse(String(init.body));
          return Promise.resolve({ ok: true, status: 201, json: async () => ({ id: "cmd-1", status: "pending" }) });
        }
        if (url.endsWith("/commands")) {
          return Promise.resolve({ ok: true, status: 200, json: async () => [{ id: "cmd-1", status: "succeeded" }] });
        }
        if (url.includes(`/api/agents/${AGENT_ID}`) && !url.includes("/commands")) {
          return Promise.resolve({ ok: true, status: 200, json: async () => AGENT_WITH_PROCESS_AND_SERVICE });
        }
        return Promise.resolve({ ok: true, json: async () => [] });
      }),
    );
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.refresh }));

    await waitFor(() => expect(refreshBody).toEqual({ command_type: "refresh_inventory", action: "collect", target: "inventory" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  // --- Faz 34: User Sessions Tracking + Quick Connect ---

  const AGENT_WITH_SESSIONS = {
    ...BASE_AGENT_DETAIL,
    latest_telemetry: {
      collected_at: "2026-01-01T00:00:00Z",
      schema_version: 1,
      cpu_percent: null,
      memory_total_bytes: null,
      memory_used_bytes: null,
      memory_percent: null,
      disks: [],
      network_interfaces: [],
      sessions: [
        { username: "Administrator", session_name: "rdp-tcp#1", status: "active", logon_time: "9/2/2026 8:57 AM" },
        { username: "jdoe", session_name: "rdp-tcp#2", status: "disconnected", logon_time: "9/1/2026 5:00 PM" },
      ],
      last_logged_in_user: "Administrator",
      active_sessions_count: 2,
    },
  };

  it("shows last logged-in user and active session count badge on Overview", async () => {
    mockAgentDetail(AGENT_WITH_SESSIONS);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    expect(screen.getByText("Administrator")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("lists session details on the Sessions tab", async () => {
    mockAgentDetail(AGENT_WITH_SESSIONS);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.sessions }));

    expect(screen.getByText("jdoe")).toBeInTheDocument();
    expect(screen.getByText("rdp-tcp#2")).toBeInTheDocument();
    expect(screen.getByText(tr.agentDetails.sessions.statusDisconnected)).toBeInTheDocument();
    expect(screen.getByText("9/1/2026 5:00 PM")).toBeInTheDocument();
  });

  it("shows honest 'no session data' when telemetry has no sessions", async () => {
    mockAgentDetail(BASE_AGENT_DETAIL);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.sessions }));

    expect(screen.getByText(tr.agentDetails.sessions.noData)).toBeInTheDocument();
  });

  it("opens the PAM Guacamole RDP page in a new tab when the agent is linked to an asset (Faz 60)", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);

    mockAgentDetail({ ...AGENT_WITH_SESSIONS, asset_id: LINKED_ASSET_ID }, 200, [LINKED_ASSET]);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.quickConnect.rdpConnect }));

    expect(openSpy).toHaveBeenCalledWith(`/pam/session/${LINKED_ASSET_ID}`, "_blank", "noopener,noreferrer");
  });

  it("opens the PAM zero-knowledge SSH page when clicking SSH Bağlan (Faz 60)", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);

    mockAgentDetail({ ...AGENT_WITH_SESSIONS, asset_id: LINKED_ASSET_ID }, 200, [LINKED_ASSET]);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.quickConnect.sshConnect }));

    expect(openSpy).toHaveBeenCalledWith(`/pam/ssh/${LINKED_ASSET_ID}`, "_blank", "noopener,noreferrer");
  });

  it("opens the web SSH terminal from the CMD/Terminal button, OS-aware label (Faz 60)", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);

    mockAgentDetail(AGENT_WITH_SESSIONS); // os: "windows"
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.quickConnect.cmdWindows }));

    expect(openSpy).toHaveBeenCalledWith(`/remote-control/ssh/${AGENT_ID}`, "_blank", "noopener,noreferrer");
  });

  it("uses the Bash label on the CMD/Terminal button for a Linux agent (Faz 60)", async () => {
    mockAgentDetail({ ...AGENT_WITH_SESSIONS, os: "linux" });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    expect(screen.getByRole("button", { name: tr.agentDetails.quickConnect.cmdLinux })).toBeInTheDocument();
  });

  it("shows a PAM hint (no RDP/SSH buttons) when the agent is not linked to an asset (Faz 60)", async () => {
    mockAgentDetail({ ...BASE_AGENT_DETAIL, asset_id: null });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    expect(screen.getByText(tr.agentDetails.quickConnect.pamNeedsLinkedAsset)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: tr.agentDetails.quickConnect.rdpConnect })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: tr.agentDetails.quickConnect.sshConnect })).not.toBeInTheDocument();
  });

  // --- Faz 37: Güç ve Oturum Yönetimi ---

  function mockAgentDetailWithPowerCommand(detail: unknown, commandOutcome: Record<string, unknown>) {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (url.endsWith("/wake") && init?.method === "POST") {
          return Promise.resolve({ ok: true, status: 200, json: async () => ({ status: "sent", mac_address: "AA-BB" }) });
        }
        if (url.includes("/commands/") === false && url.endsWith("/commands") && init?.method === "POST") {
          return Promise.resolve({
            ok: true,
            status: 201,
            json: async () => ({ id: "cmd-1", status: "pending", result_detail: null, ...JSON.parse(String(init.body)) }),
          });
        }
        if (url.endsWith("/commands")) {
          return Promise.resolve({ ok: true, status: 200, json: async () => [{ id: "cmd-1", ...commandOutcome }] });
        }
        if (url.includes(`/api/agents/${AGENT_ID}`) && !url.includes("/commands") && !url.endsWith("/wake")) {
          return Promise.resolve({ ok: true, status: 200, json: async () => detail });
        }
        return Promise.resolve({ ok: true, json: async () => [] });
      }),
    );
  }

  async function openPowerMenu() {
    fireEvent.click(screen.getByRole("button", { name: tr.powerActions.title }));
  }

  it("shows a confirmation modal with the hostname before rebooting", async () => {
    mockAgentDetailWithPowerCommand(BASE_AGENT_DETAIL, { status: "succeeded" });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    await openPowerMenu();
    fireEvent.click(screen.getByRole("button", { name: tr.powerActions.reboot }));

    expect(
      screen.getByText(tr.agentCommands.confirmPower("win-server-01", tr.agentCommands.actionReboot)),
    ).toBeInTheDocument();
  });

  it("submits a power_control/reboot command on confirm and shows a success toast", async () => {
    mockAgentDetailWithPowerCommand(BASE_AGENT_DETAIL, { status: "succeeded" });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    await openPowerMenu();
    fireEvent.click(screen.getByRole("button", { name: tr.powerActions.reboot }));
    fireEvent.click(screen.getByRole("button", { name: tr.agentCommands.confirmButton }));

    expect(await screen.findByText(tr.agentCommands.successPower(tr.powerActions.reboot))).toBeInTheDocument();
  });

  it("shows a confirmation modal before shutting down", async () => {
    mockAgentDetailWithPowerCommand(BASE_AGENT_DETAIL, { status: "succeeded" });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    await openPowerMenu();
    fireEvent.click(screen.getByRole("button", { name: tr.powerActions.shutdown }));

    expect(
      screen.getByText(tr.agentCommands.confirmPower("win-server-01", tr.agentCommands.actionShutdown)),
    ).toBeInTheDocument();
  });

  it("shows a confirmation modal before logging off", async () => {
    mockAgentDetailWithPowerCommand(BASE_AGENT_DETAIL, { status: "succeeded" });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    await openPowerMenu();
    fireEvent.click(screen.getByRole("button", { name: tr.powerActions.logoff }));

    expect(
      screen.getByText(tr.agentCommands.confirmPower("win-server-01", tr.agentCommands.actionLogoff)),
    ).toBeInTheDocument();
  });

  it("sends a Wake-on-LAN request without a confirmation modal", async () => {
    mockAgentDetailWithPowerCommand(BASE_AGENT_DETAIL, { status: "succeeded" });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    await openPowerMenu();
    fireEvent.click(screen.getByRole("button", { name: tr.powerActions.wake }));

    expect(await screen.findByText(tr.agentCommands.wakeSent)).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("keeps Wake-on-LAN clickable even when the agent is offline", async () => {
    mockAgentDetailWithPowerCommand({ ...BASE_AGENT_DETAIL, status: "offline" }, { status: "succeeded" });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    await openPowerMenu();

    expect(screen.getByRole("button", { name: tr.powerActions.wake })).not.toBeDisabled();
  });

  it("disables Wake-on-LAN when the agent has no known MAC address", async () => {
    mockAgentDetailWithPowerCommand({ ...BASE_AGENT_DETAIL, mac_address: null }, { status: "succeeded" });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    await openPowerMenu();

    expect(screen.getByRole("button", { name: tr.powerActions.wake })).toBeDisabled();
  });

  // --- Windows Update Tarama Motoru ---

  function mockAgentDetailWithUpdates(detail: unknown, updatesResponse: { status: number; body?: unknown }) {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes(`/api/agents/${AGENT_ID}/updates`)) {
          return Promise.resolve({
            ok: updatesResponse.status < 400,
            status: updatesResponse.status,
            json: async () => updatesResponse.body ?? {},
          });
        }
        if (url.includes(`/api/agents/${AGENT_ID}`)) {
          return Promise.resolve({ ok: true, status: 200, json: async () => detail });
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => [] });
      }),
    );
  }

  it("shows a linux-unsupported message on the Windows Updates tab for a Linux agent", async () => {
    mockAgentDetailWithUpdates({ ...BASE_AGENT_DETAIL, os: "linux" }, { status: 404 });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));

    expect(screen.getByText(tr.agentDetails.windowsUpdates.linuxUnsupported)).toBeInTheDocument();
  });

  it("shows 'never scanned' when the agent has no recorded scan yet", async () => {
    mockAgentDetailWithUpdates(BASE_AGENT_DETAIL, { status: 404 });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));

    expect(await screen.findByText(tr.agentDetails.windowsUpdates.neverScanned)).toBeInTheDocument();
  });

  it("shows real pending updates from a COM scan", async () => {
    mockAgentDetailWithUpdates(BASE_AGENT_DETAIL, {
      status: 200,
      body: {
        agent_id: AGENT_ID,
        collected_at: "2026-09-01T00:00:00Z",
        scan_method: "com",
        is_admin: true,
        updates: [
          { kb_number: "KB5001234", title: "2026-09 Cumulative Update", description: null, size_bytes: 500_000_000 },
        ],
        error: null,
      },
    });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));

    expect(await screen.findByText("KB5001234")).toBeInTheDocument();
    expect(screen.getByText("2026-09 Cumulative Update")).toBeInTheDocument();
    expect(screen.getByText(tr.agentDetails.windowsUpdates.scanMethodLabels.com)).toBeInTheDocument();
    expect(screen.queryByText(tr.agentDetails.windowsUpdates.fallbackNotice)).not.toBeInTheDocument();
  });

  it("shows a fallback notice and never mislabels installed hotfixes as pending updates", async () => {
    mockAgentDetailWithUpdates(BASE_AGENT_DETAIL, {
      status: 200,
      body: {
        agent_id: AGENT_ID,
        collected_at: "2026-09-01T00:00:00Z",
        scan_method: "installed_hotfixes",
        is_admin: true,
        updates: [{ kb_number: "KB999", title: "Already installed", description: null, size_bytes: null }],
        error: "COM taraması başarısız oldu: COM not registered",
      },
    });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));

    expect(await screen.findByText(tr.agentDetails.windowsUpdates.fallbackNotice)).toBeInTheDocument();
    expect(screen.getByText(tr.agentDetails.windowsUpdates.scanMethodLabels.installed_hotfixes)).toBeInTheDocument();
  });

  it("shows 'no pending updates' when a COM scan found nothing", async () => {
    mockAgentDetailWithUpdates(BASE_AGENT_DETAIL, {
      status: 200,
      body: {
        agent_id: AGENT_ID,
        collected_at: "2026-09-01T00:00:00Z",
        scan_method: "com",
        is_admin: true,
        updates: [],
        error: null,
      },
    });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));

    expect(await screen.findByText(tr.agentDetails.windowsUpdates.noUpdates)).toBeInTheDocument();
  });

  // --- "Güncellemeleri Kontrol Et" butonu ---

  function mockAgentDetailWithCheckUpdatesCommand(commandOutcome: Record<string, unknown>, afterScan: unknown) {
    let updatesCallCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (url.endsWith("/commands") && init?.method === "POST") {
          return Promise.resolve({
            ok: true,
            status: 201,
            json: async () => ({ id: "cmd-1", status: "pending", result_detail: null, ...JSON.parse(String(init.body)) }),
          });
        }
        if (url.endsWith("/commands")) {
          return Promise.resolve({ ok: true, status: 200, json: async () => [{ id: "cmd-1", ...commandOutcome }] });
        }
        if (url.includes(`/api/agents/${AGENT_ID}/updates`)) {
          updatesCallCount += 1;
          // İlk çağrı (mount) — henüz tarama yok; komut başarıyla
          // tamamlandıktan SONRAki çağrı(lar) — taze sonucu döner.
          if (updatesCallCount === 1) {
            return Promise.resolve({ ok: false, status: 404, json: async () => ({}) });
          }
          return Promise.resolve({ ok: true, status: 200, json: async () => afterScan });
        }
        if (url.includes(`/api/agents/${AGENT_ID}`)) {
          return Promise.resolve({ ok: true, status: 200, json: async () => BASE_AGENT_DETAIL });
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => [] });
      }),
    );
  }

  it("submits a check_updates command and refreshes the table on success", async () => {
    mockAgentDetailWithCheckUpdatesCommand(
      { status: "succeeded", result_detail: "1 güncelleme bulundu (com)" },
      {
        agent_id: AGENT_ID,
        collected_at: "2026-09-03T12:00:00Z",
        scan_method: "com",
        is_admin: true,
        updates: [{ kb_number: "KB9999999", title: "Fresh scan result", description: null, size_bytes: null }],
        error: null,
      },
    );
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));
    expect(await screen.findByText(tr.agentDetails.windowsUpdates.neverScanned)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.windowsUpdates.checkNow }));

    expect(await screen.findByText("KB9999999")).toBeInTheDocument();
    expect(screen.getByText("Fresh scan result")).toBeInTheDocument();
  });

  it("shows a loading notice while the check_updates command is in flight", async () => {
    mockAgentDetailWithCheckUpdatesCommand({ status: "pending" }, null);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));
    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.windowsUpdates.checkNow }));

    expect(await screen.findByText(tr.agentDetails.windowsUpdates.checking)).toBeInTheDocument();
  });

  it("shows a failure toast when the check_updates command fails", async () => {
    mockAgentDetailWithCheckUpdatesCommand(
      { status: "failed", result_detail: "Hem COM hem PowerShell başarısız oldu" },
      null,
    );
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));
    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.windowsUpdates.checkNow }));

    expect(await screen.findByText(tr.agentCommands.failure("Hem COM hem PowerShell başarısız oldu"))).toBeInTheDocument();
  });

  it("does not show the check-updates button for a Linux agent", async () => {
    mockAgentDetailWithUpdates({ ...BASE_AGENT_DETAIL, os: "linux" }, { status: 404 });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));

    expect(screen.queryByRole("button", { name: tr.agentDetails.windowsUpdates.checkNow })).not.toBeInTheDocument();
  });

  // --- KB link, açıklama paneli, reboot banner ---

  it("links the KB number to the official Microsoft Support page", async () => {
    mockAgentDetailWithUpdates(BASE_AGENT_DETAIL, {
      status: 200,
      body: {
        agent_id: AGENT_ID, collected_at: "2026-09-01T00:00:00Z", scan_method: "com", is_admin: true,
        updates: [{ kb_number: "KB5001234", title: "Update", description: null, size_bytes: null }],
        error: null, reboot_required: false,
      },
    });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));

    const link = await screen.findByRole("link", { name: "KB5001234" });
    expect(link).toHaveAttribute("href", "https://support.microsoft.com/help/5001234");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("expands and collapses the update description on click", async () => {
    mockAgentDetailWithUpdates(BASE_AGENT_DETAIL, {
      status: 200,
      body: {
        agent_id: AGENT_ID, collected_at: "2026-09-01T00:00:00Z", scan_method: "com", is_admin: true,
        updates: [{ kb_number: "KB5001234", title: "Cumulative Update", description: "Fixes a security issue.", size_bytes: null }],
        error: null, reboot_required: false,
      },
    });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));
    await screen.findByText("Cumulative Update");

    expect(screen.queryByText("Fixes a security issue.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cumulative Update" }));
    expect(await screen.findByText("Fixes a security issue.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cumulative Update" }));
    expect(screen.queryByText("Fixes a security issue.")).not.toBeInTheDocument();
  });

  it("shows a reboot-required banner with a restart shortcut", async () => {
    mockAgentDetailWithUpdates(BASE_AGENT_DETAIL, {
      status: 200,
      body: {
        agent_id: AGENT_ID, collected_at: "2026-09-01T00:00:00Z", scan_method: "com", is_admin: true,
        updates: [], error: null, reboot_required: true,
      },
    });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));

    expect(await screen.findByText(tr.agentDetails.windowsUpdates.rebootRequiredBanner)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.windowsUpdates.rebootNow }));
    expect(
      await screen.findByText(tr.agentCommands.confirmPower("win-server-01", tr.agentCommands.actionReboot)),
    ).toBeInTheDocument();
  });

  it("does not show install buttons for installed-hotfixes fallback results", async () => {
    mockAgentDetailWithUpdates(BASE_AGENT_DETAIL, {
      status: 200,
      body: {
        agent_id: AGENT_ID, collected_at: "2026-09-01T00:00:00Z", scan_method: "installed_hotfixes", is_admin: true,
        updates: [{ kb_number: "KB999", title: "Already installed", description: null, size_bytes: null }],
        error: "COM taraması başarısız oldu", reboot_required: false,
      },
    });
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));
    await screen.findByText("Already installed");

    expect(screen.queryByRole("button", { name: tr.agentDetails.windowsUpdates.installNow })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: tr.agentDetails.windowsUpdates.installAll })).not.toBeInTheDocument();
  });

  // --- "Şimdi Yükle" / "Tümünü Yükle" ---

  function mockAgentDetailWithInstallCommand(commandOutcome: Record<string, unknown>, afterInstall: unknown) {
    const scanBefore = {
      agent_id: AGENT_ID, collected_at: "2026-09-01T00:00:00Z", scan_method: "com", is_admin: true,
      updates: [{ kb_number: "KB5001234", title: "Cumulative Update", description: null, size_bytes: 500_000_000 }],
      error: null, reboot_required: false,
    };
    let updatesCallCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (url.endsWith("/commands") && init?.method === "POST") {
          return Promise.resolve({
            ok: true, status: 201,
            json: async () => ({ id: "cmd-1", status: "pending", result_detail: null, ...JSON.parse(String(init.body)) }),
          });
        }
        if (url.endsWith("/commands")) {
          return Promise.resolve({ ok: true, status: 200, json: async () => [{ id: "cmd-1", ...commandOutcome }] });
        }
        if (url.includes(`/api/agents/${AGENT_ID}/updates`)) {
          updatesCallCount += 1;
          if (updatesCallCount === 1) {
            return Promise.resolve({ ok: true, status: 200, json: async () => scanBefore });
          }
          return Promise.resolve({ ok: true, status: 200, json: async () => afterInstall });
        }
        if (url.includes(`/api/agents/${AGENT_ID}`)) {
          return Promise.resolve({ ok: true, status: 200, json: async () => BASE_AGENT_DETAIL });
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => [] });
      }),
    );
  }

  it("asks for confirmation before installing a single update, then refreshes on success", async () => {
    mockAgentDetailWithInstallCommand(
      { status: "succeeded", result_detail: "1 güncelleme başarıyla yüklendi" },
      { agent_id: AGENT_ID, collected_at: "2026-09-03T12:00:00Z", scan_method: "com", is_admin: true, updates: [], error: null, reboot_required: false },
    );
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));
    await screen.findByText("Cumulative Update");

    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.windowsUpdates.installNow }));
    expect(
      await screen.findByText(tr.agentDetails.windowsUpdates.confirmInstallOne("KB5001234")),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: tr.agentCommands.confirmButton }));

    expect(await screen.findByText(tr.agentDetails.windowsUpdates.noUpdates)).toBeInTheDocument();
  });

  it("cancelling the install confirmation submits no command", async () => {
    const fetchSpy = vi.fn((url: string, init?: RequestInit) => {
      void init;
      if (url.includes(`/api/agents/${AGENT_ID}/updates`)) {
        return Promise.resolve({
          ok: true, status: 200,
          json: async () => ({
            agent_id: AGENT_ID, collected_at: "2026-09-01T00:00:00Z", scan_method: "com", is_admin: true,
            updates: [{ kb_number: "KB5001234", title: "Cumulative Update", description: null, size_bytes: null }],
            error: null, reboot_required: false,
          }),
        });
      }
      if (url.includes(`/api/agents/${AGENT_ID}`)) {
        return Promise.resolve({ ok: true, status: 200, json: async () => BASE_AGENT_DETAIL });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => [] });
    });
    vi.stubGlobal("fetch", fetchSpy);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));
    await screen.findByText("Cumulative Update");

    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.windowsUpdates.installNow }));
    await screen.findByText(tr.agentDetails.windowsUpdates.confirmInstallOne("KB5001234"));
    fireEvent.click(screen.getByRole("button", { name: tr.agentCommands.cancelButton }));

    expect(screen.queryByText(tr.agentDetails.windowsUpdates.confirmInstallOne("KB5001234"))).not.toBeInTheDocument();
    expect(fetchSpy.mock.calls.some(([url, init]) => url.endsWith("/commands") && init?.method === "POST")).toBe(false);
  });

  it("shows the correct confirmation message for Install All", async () => {
    mockAgentDetailWithInstallCommand({ status: "succeeded", result_detail: "ok" }, null);
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));
    await screen.findByText("Cumulative Update");

    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.windowsUpdates.installAll }));
    expect(await screen.findByText(tr.agentDetails.windowsUpdates.confirmInstallAll(1))).toBeInTheDocument();
  });

  it("shows a failure toast when the install_update command fails", async () => {
    mockAgentDetailWithInstallCommand(
      { status: "failed", result_detail: "İndirme başarısız oldu (ResultCode=4)" },
      null,
    );
    renderWithDashboardData(<AgentDetailView agentId={AGENT_ID} />);

    await screen.findByRole("heading", { name: "win-server-01" });
    fireEvent.click(screen.getByRole("tab", { name: tr.agentDetails.tabs.windowsUpdates }));
    await screen.findByText("Cumulative Update");

    fireEvent.click(screen.getByRole("button", { name: tr.agentDetails.windowsUpdates.installNow }));
    await screen.findByText(tr.agentDetails.windowsUpdates.confirmInstallOne("KB5001234"));
    fireEvent.click(screen.getByRole("button", { name: tr.agentCommands.confirmButton }));

    expect(
      await screen.findByText(tr.agentDetails.windowsUpdates.installFailure("İndirme başarısız oldu (ResultCode=4)")),
    ).toBeInTheDocument();
  });
});
