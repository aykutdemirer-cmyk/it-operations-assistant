"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import {
  agentRdpConnectUrl,
  ApiError,
  fetchAgent,
  pollAgentCommand,
  submitAgentCommand,
  wakeAgent,
  type AgentCommandAction,
  type AgentCommandType,
  type AgentDetail,
  type AgentProcessInfo,
} from "@/lib/api";
import { useDashboardData } from "@/lib/DashboardDataProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { timeAgo } from "@/lib/time";
import { ConfirmModal } from "./ConfirmModal";
import { ToastStack, useToasts } from "./Toast";
import styles from "./AgentDetailView.module.css";

type FetchStatus = "loading" | "done" | "error" | "not_found";
type TabKey =
  | "overview"
  | "system"
  | "cpu"
  | "memory"
  | "disk"
  | "network"
  | "processes"
  | "services"
  | "sessions";

function formatBytes(bytes: number | null): string {
  if (bytes == null) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

function formatSpeed(bps: number | null): string {
  if (bps == null) return "-";
  const mbps = bps / 1_000_000;
  return `${mbps.toFixed(0)} Mbps`;
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString();
}

function statusDotClass(status: AgentDetail["status"], styles: Record<string, string>): string {
  if (status === "online") return styles.dotOnline;
  if (status === "offline") return styles.dotOffline;
  return styles.dotUnknown;
}

// PID 0 ("System Idle Process" / Linux'ta genelde yok) işletim
// sisteminin BOŞTA KALMA oranını temsil eder — gerçek bir "süreç"
// değildir. Tablodan GİZLENMEZ (dürüst veri ilkesi) ama açıkça
// etiketlenir; CPU sıralamasında en üstte çıkıp asıl yoğun süreçleri
// gölgelememesi için varsayılan sıralamada göz ardı edilebilir olsun
// diye ayrı bir bayrak taşır (bkz. `ProcessRow`).
const IDLE_PROCESS_PID = 0;

type ProcessSortColumn = "pid" | "name" | "cpu_percent" | "memory_percent" | "username" | "status";
type SortDirection = "asc" | "desc";

function sortAndFilterProcesses(
  processes: AgentProcessInfo[],
  search: string,
  sortColumn: ProcessSortColumn,
  sortDirection: SortDirection
) {
  const needle = search.trim().toLowerCase();
  const filtered = needle
    ? processes.filter(
        (p) => p.name.toLowerCase().includes(needle) || String(p.pid).includes(needle)
      )
    : processes;

  const sorted = [...filtered].sort((a, b) => {
    let cmp: number;
    if (sortColumn === "pid") cmp = a.pid - b.pid;
    else if (sortColumn === "cpu_percent") cmp = (a.cpu_percent ?? -1) - (b.cpu_percent ?? -1);
    else if (sortColumn === "memory_percent") cmp = (a.memory_percent ?? -1) - (b.memory_percent ?? -1);
    else if (sortColumn === "name") cmp = a.name.localeCompare(b.name);
    else if (sortColumn === "username") cmp = (a.username ?? "").localeCompare(b.username ?? "");
    else cmp = (a.status ?? "").localeCompare(b.status ?? "");
    return sortDirection === "asc" ? cmp : -cmp;
  });
  return sorted;
}

type Props = {
  agentId: string;
};

export function AgentDetailView({ agentId }: Props) {
  const { t } = useLocale();
  const { assets } = useDashboardData();
  const d = t.agentDetails;
  const cmdText = t.agentCommands;

  const [agent, setAgent] = useState<AgentDetail | null>(null);
  const [status, setStatus] = useState<FetchStatus>("loading");
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const { toasts, push: pushToast, dismiss: dismissToast } = useToasts();
  const [pendingAction, setPendingAction] = useState<{
    commandType: AgentCommandType;
    action: AgentCommandAction;
    target: string;
    label: string;
  } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [powerMenuOpen, setPowerMenuOpen] = useState(false);
  const [waking, setWaking] = useState(false);
  const [processSearch, setProcessSearch] = useState("");
  const [processSort, setProcessSort] = useState<{ column: ProcessSortColumn; direction: SortDirection }>({
    column: "cpu_percent",
    direction: "desc",
  });

  const handleProcessSort = (column: ProcessSortColumn) => {
    setProcessSort((prev) =>
      prev.column === column
        ? { column, direction: prev.direction === "asc" ? "desc" : "asc" }
        : { column, direction: "desc" }
    );
  };

  const loadAgent = useCallback(() => {
    return fetchAgent(agentId)
      .then((data) => {
        setAgent(data);
        setStatus("done");
      })
      .catch((err) => {
        setStatus(err instanceof ApiError && err.status === 404 ? "not_found" : "error");
      });
  }, [agentId]);

  useEffect(() => {
    loadAgent();
  }, [loadAgent]);

  const handleConfirmAction = async () => {
    if (!pendingAction) return;
    setSubmitting(true);
    try {
      const created = await submitAgentCommand(agentId, {
        command_type: pendingAction.commandType,
        action: pendingAction.action,
        target: pendingAction.target,
      });

      if (created.status === "rejected") {
        pushToast("error", cmdText.failure(created.result_detail ?? "reddedildi"));
      } else {
        const finalCommand = await pollAgentCommand(agentId, created.id);
        if (!finalCommand || finalCommand.status === "pending" || finalCommand.status === "sent") {
          pushToast("error", cmdText.stillProcessing);
        } else if (finalCommand.status === "succeeded") {
          const message =
            pendingAction.commandType === "kill_process"
              ? cmdText.successKill(pendingAction.target)
              : pendingAction.commandType === "power_control"
                ? cmdText.successPower(pendingAction.label)
                : cmdText.successService(pendingAction.target);
          pushToast("success", message);
        } else {
          pushToast("error", cmdText.failure(finalCommand.result_detail ?? "başarısız"));
        }
      }
    } catch (err) {
      pushToast("error", cmdText.failure(err instanceof Error ? err.message : String(err)));
    } finally {
      setSubmitting(false);
      setPendingAction(null);
      // Agent, komut sonucunu bildirdikten HEMEN SONRA taze bir envanter
      // gönderiyor (bkz. `agent/main.py::_poll_and_execute_commands`) —
      // ama bu ikinci istek ayrı bir ağ round-trip'i, komut sonucunun
      // kendisinden az da olsa GEÇ tamamlanabilir. Kısa bir tampon
      // olmadan burada yenilersek eski (değişmemiş) envanteri
      // görebiliriz — kullanıcı bildirimiyle bulunan gerçek bir sorun.
      await loadAgent();
      setTimeout(loadAgent, 1500);
    }
  };

  const handleManualRefresh = async () => {
    // Faz 33.1 — kullanıcı bildirimi: yeni açılan bir process ya da
    // durdurulan bir servis, normal 5 dakikalık envanter turu dolana
    // kadar ekranda görünmüyordu. Bu buton agent'a HEMEN taze bir
    // envanter göndermesini söyler (`refresh_inventory` komutu) —
    // agent kapalıysa/`ENABLE_REMOTE_COMMANDS=false` ise dürüstçe
    // "hâlâ işleniyor" durumuna düşer, sahte bir başarı GÖSTERİLMEZ.
    setRefreshing(true);
    try {
      const created = await submitAgentCommand(agentId, {
        command_type: "refresh_inventory",
        action: "collect",
        target: "inventory",
      });
      if (created.status === "rejected") {
        pushToast("error", cmdText.failure(created.result_detail ?? "reddedildi"));
      } else {
        const finalCommand = await pollAgentCommand(agentId, created.id);
        if (!finalCommand || finalCommand.status === "pending" || finalCommand.status === "sent") {
          pushToast("error", cmdText.stillProcessing);
        } else if (finalCommand.status !== "succeeded") {
          pushToast("error", cmdText.failure(finalCommand.result_detail ?? "başarısız"));
        }
      }
    } catch (err) {
      pushToast("error", cmdText.failure(err instanceof Error ? err.message : String(err)));
    } finally {
      setRefreshing(false);
      await loadAgent();
    }
  };

  const handleWake = async () => {
    // Faz 37 — Wake-on-LAN. Agent'ın kendisiyle HİÇ konuşmaz — cihaz
    // Çevrimdışıyken de çağrılabilir, bu yüzden mevcut `pendingAction`/
    // `submitAgentCommand` (agent_commands kuyruğu) akışını KULLANMAZ,
    // doğrudan `POST /api/agents/{id}/wake`'i çağırır. Onay modalı YOK
    // — geri dönüşü olmayan bir işlem değil, yalnızca bir ağ paketi.
    setPowerMenuOpen(false);
    setWaking(true);
    try {
      await wakeAgent(agentId);
      pushToast("success", cmdText.wakeSent);
    } catch (err) {
      pushToast("error", cmdText.failure(err instanceof Error ? err.message : String(err)));
    } finally {
      setWaking(false);
    }
  };

  const requestPowerAction = (action: "reboot" | "shutdown" | "logoff", actionLabel: string) => {
    setPowerMenuOpen(false);
    setPendingAction({
      commandType: "power_control",
      action,
      // Backend `target` boş string kabul etmiyor — logoff için Linux'ta
      // gerçek hedef kullanıcı adı anlamlı (bkz. agent/commands.py),
      // Windows'ta zaten yok sayılıyor. reboot/shutdown'da target hiç
      // kullanılmaz, sabit bir yer tutucu yeterli.
      target: action === "logoff" ? (agent?.latest_telemetry?.last_logged_in_user ?? "current") : "system",
      label: actionLabel,
    });
  };

  const linkedAsset = agent?.asset_id ? assets.find((a) => a.id === agent.asset_id) : undefined;

  const TABS: { key: TabKey; label: string }[] = [
    { key: "overview", label: d.tabs.overview },
    { key: "system", label: d.tabs.system },
    { key: "cpu", label: d.tabs.cpu },
    { key: "memory", label: d.tabs.memory },
    { key: "disk", label: d.tabs.disk },
    { key: "network", label: d.tabs.network },
    { key: "processes", label: d.tabs.processes },
    { key: "services", label: d.tabs.services },
    { key: "sessions", label: d.tabs.sessions },
  ];

  if (status === "loading") {
    return <p className={styles.status}>{t.common.loading}</p>;
  }
  if (status === "not_found") {
    return <p className={styles.error}>{d.notFound}</p>;
  }
  if (status === "error" || !agent) {
    return <p className={styles.error}>{d.loadError}</p>;
  }

  const telemetry = agent.latest_telemetry;
  const inventory = agent.inventory;
  const networkInterfaces = telemetry?.network_interfaces ?? inventory?.network_interfaces ?? [];

  return (
    <section className={styles.card} aria-label={d.ariaLabel}>
      <Link className={styles.backLink} href="/agents">
        ← {d.backToList}
      </Link>

      <div className={styles.header}>
        <h2 className={styles.title}>{agent.hostname}</h2>
        <span className={styles.statusCell}>
          <span className={`${styles.dot} ${statusDotClass(agent.status, styles)}`} />
          {t.agents.statusLabels[agent.status]}
        </span>

        <div className={styles.quickConnect}>
          {agent.local_ip ? (
            <>
              <a
                className={styles.quickConnectButton}
                href={agentRdpConnectUrl(agent.id)}
                download
                title={agent.local_ip}
              >
                {d.quickConnect.rdp}
              </a>
              {/* Faz 35 — SSH artık .rdp gibi bir indirme/URI DEĞİL, tam
                  bir web terminali (xterm.js) açan yeni bir sekme.
                  Kimlik bilgisi backend'e ASLA bu sayfadan geçmez —
                  yalnızca `/remote-control/ssh/{agentId}` kendi login
                  formunda istenir (bkz. `components/SshTerminal.tsx`). */}
              <button
                type="button"
                className={styles.quickConnectButton}
                onClick={() => window.open(`/remote-control/ssh/${agent.id}`, "_blank", "noopener,noreferrer")}
              >
                {d.quickConnect.ssh}
              </button>
            </>
          ) : (
            <span className={styles.quickConnectUnavailable}>{d.quickConnect.unavailable}</span>
          )}

          {/* Faz 37 — Güç ve Oturum Yönetimi. Reboot/Shutdown/Logoff
              mevcut agent_commands kuyruğu üzerinden gider (onay modalı
              zorunlu — geri dönüşü yok). Wake-on-LAN AYRI bir yol:
              agent'ın kendisiyle hiç konuşmaz, cihaz Çevrimdışıyken de
              tıklanabilir olması GEREKİYOR (bkz. buton `disabled` KOŞULU
              — WoL için asla devre dışı bırakılmaz). */}
          <div className={styles.powerMenuWrap}>
            <button
              type="button"
              className={styles.powerMenuButton}
              onClick={() => setPowerMenuOpen((open) => !open)}
            >
              {t.powerActions.title}
            </button>
            {powerMenuOpen && (
              <div className={styles.powerMenu}>
                <button
                  type="button"
                  className={styles.powerMenuItem}
                  disabled={!agent.local_ip}
                  onClick={() => requestPowerAction("reboot", t.powerActions.reboot)}
                >
                  {t.powerActions.reboot}
                </button>
                <button
                  type="button"
                  className={styles.powerMenuItem}
                  disabled={!agent.local_ip}
                  onClick={() => requestPowerAction("shutdown", t.powerActions.shutdown)}
                >
                  {t.powerActions.shutdown}
                </button>
                <button
                  type="button"
                  className={styles.powerMenuItem}
                  disabled={!agent.local_ip}
                  onClick={() => requestPowerAction("logoff", t.powerActions.logoff)}
                >
                  {t.powerActions.logoff}
                </button>
                <button
                  type="button"
                  className={styles.powerMenuItem}
                  disabled={waking || !agent.mac_address}
                  onClick={handleWake}
                >
                  {t.powerActions.wake}
                </button>
              </div>
            )}
          </div>
        </div>

        <button type="button" className={styles.refreshButton} onClick={handleManualRefresh} disabled={refreshing}>
          {refreshing ? cmdText.processing : d.refresh}
        </button>
      </div>

      <div className={styles.tabs} role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.key}
            className={`${styles.tab} ${activeTab === tab.key ? styles.tabActive : ""}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "overview" && (
        <dl className={styles.fields}>
          <div className={styles.field}>
            <dt>{d.fields.hostname}</dt>
            <dd>{agent.hostname}</dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.fqdn}</dt>
            <dd>{agent.fqdn ?? "-"}</dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.os}</dt>
            <dd>{agent.os}</dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.osVersion}</dt>
            <dd>{agent.os_version ?? "-"}</dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.architecture}</dt>
            <dd>{agent.architecture ?? "-"}</dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.agentVersion}</dt>
            <dd>{agent.agent_version}</dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.localIp}</dt>
            <dd className={styles.mono}>{agent.local_ip ?? "-"}</dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.macAddress}</dt>
            <dd className={styles.mono}>{agent.mac_address ?? "-"}</dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.registeredAt}</dt>
            <dd>{formatTimestamp(agent.registered_at)}</dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.lastHeartbeat}</dt>
            <dd>{agent.last_heartbeat_at ? timeAgo(agent.last_heartbeat_at, t.timeAgo) : t.common.noDataAvailable}</dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.asset}</dt>
            <dd>
              {linkedAsset ? (linkedAsset.hostname ?? linkedAsset.ip_address) : d.notAssignedToAsset}
            </dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.capabilities}</dt>
            <dd>{agent.capabilities.length > 0 ? agent.capabilities.join(", ") : "-"}</dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.lastLoggedInUser}</dt>
            <dd>{telemetry?.last_logged_in_user ?? t.common.noDataAvailable}</dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.activeSessions}</dt>
            <dd>
              {telemetry?.active_sessions_count != null ? (
                <span className={styles.sessionBadge}>{telemetry.active_sessions_count}</span>
              ) : (
                t.common.noDataAvailable
              )}
            </dd>
          </div>
        </dl>
      )}

      {activeTab === "system" && (
        <dl className={styles.fields}>
          {inventory?.os ? (
            <>
              <div className={styles.field}>
                <dt>{d.fields.os}</dt>
                <dd>{inventory.os.name ?? "-"}</dd>
              </div>
              <div className={styles.field}>
                <dt>{d.fields.osVersion}</dt>
                <dd>{inventory.os.version ?? "-"}</dd>
              </div>
              <div className={styles.field}>
                <dt>{d.fields.architecture}</dt>
                <dd>{inventory.os.architecture ?? "-"}</dd>
              </div>
              <div className={styles.field}>
                <dt>{d.fields.manufacturer}</dt>
                <dd>{inventory.hardware?.manufacturer ?? "-"}</dd>
              </div>
              <div className={styles.field}>
                <dt>{d.fields.model}</dt>
                <dd>{inventory.hardware?.model ?? "-"}</dd>
              </div>
            </>
          ) : (
            <p className={styles.noData}>{d.noInventoryData}</p>
          )}
        </dl>
      )}

      {activeTab === "cpu" && (
        <dl className={styles.fields}>
          <div className={styles.field}>
            <dt>{d.fields.cpuModel}</dt>
            <dd>{inventory?.hardware?.cpu_model ?? "-"}</dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.cpuCores}</dt>
            <dd>{inventory?.hardware?.cpu_cores ?? "-"}</dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.cpuLogical}</dt>
            <dd>{inventory?.hardware?.cpu_logical_processors ?? "-"}</dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.cpuUsage}</dt>
            <dd className={telemetry?.cpu_percent == null ? styles.noData : undefined}>
              {telemetry?.cpu_percent != null ? `${telemetry.cpu_percent.toFixed(1)}%` : d.noTelemetryData}
            </dd>
          </div>
        </dl>
      )}

      {activeTab === "memory" && (
        <dl className={styles.fields}>
          <div className={styles.field}>
            <dt>{d.fields.memoryTotal}</dt>
            <dd>{formatBytes(telemetry?.memory_total_bytes ?? inventory?.hardware?.total_memory_bytes ?? null)}</dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.memoryUsed}</dt>
            <dd className={telemetry?.memory_used_bytes == null ? styles.noData : undefined}>
              {telemetry?.memory_used_bytes != null ? formatBytes(telemetry.memory_used_bytes) : d.noTelemetryData}
            </dd>
          </div>
          <div className={styles.field}>
            <dt>{d.fields.memoryPercent}</dt>
            <dd className={telemetry?.memory_percent == null ? styles.noData : undefined}>
              {telemetry?.memory_percent != null ? `${telemetry.memory_percent.toFixed(1)}%` : d.noTelemetryData}
            </dd>
          </div>
        </dl>
      )}

      {activeTab === "disk" && (
        <div>
          {telemetry && telemetry.disks.length > 0 ? (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>{d.disk.device}</th>
                  <th>{d.disk.usage}</th>
                  <th>{d.disk.percent}</th>
                </tr>
              </thead>
              <tbody>
                {telemetry.disks.map((disk) => (
                  <tr key={disk.device}>
                    <td className={styles.mono}>{disk.device}</td>
                    <td>
                      {formatBytes(disk.used_bytes)} / {formatBytes(disk.total_bytes)}
                    </td>
                    <td>{disk.percent != null ? `${disk.percent.toFixed(1)}%` : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className={styles.noData}>{d.noTelemetryData}</p>
          )}
        </div>
      )}

      {activeTab === "network" && (
        <div>
          {networkInterfaces.length > 0 ? (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>{d.network.name}</th>
                    <th>{d.network.type}</th>
                    <th>{d.network.address}</th>
                    <th>{d.network.mac}</th>
                    <th>{d.network.state}</th>
                    <th>{d.network.speed}</th>
                  </tr>
                </thead>
                <tbody>
                  {networkInterfaces.map((iface) => (
                    <tr key={iface.name}>
                      <td>{iface.name}</td>
                      <td>{iface.interface_type ?? "-"}</td>
                      <td className={styles.mono}>{iface.addresses.join(", ") || iface.ip_address || "-"}</td>
                      <td className={styles.mono}>{iface.mac_address ?? "-"}</td>
                      <td>{iface.state ?? "-"}</td>
                      <td>{formatSpeed(iface.speed_bps)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className={styles.noData}>{d.noTelemetryData}</p>
          )}
        </div>
      )}

      {activeTab === "processes" && (
        <div>
          {inventory && inventory.processes.length > 0 ? (
            <>
              <input
                type="text"
                className={styles.searchInput}
                placeholder={d.processes.searchPlaceholder}
                value={processSearch}
                onChange={(e) => setProcessSearch(e.target.value)}
                aria-label={d.processes.searchPlaceholder}
              />
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      {(
                        [
                          ["pid", d.processes.pid],
                          ["name", d.processes.name],
                          ["cpu_percent", d.processes.cpu],
                          ["memory_percent", d.processes.memory],
                          ["username", d.processes.user],
                          ["status", d.processes.status],
                        ] as [ProcessSortColumn, string][]
                      ).map(([column, label]) => (
                        <th key={column}>
                          <button
                            type="button"
                            className={styles.sortableHeader}
                            onClick={() => handleProcessSort(column)}
                          >
                            {label}
                            {processSort.column === column && (
                              <span aria-hidden="true">{processSort.direction === "asc" ? " ▲" : " ▼"}</span>
                            )}
                          </button>
                        </th>
                      ))}
                      <th>{d.processes.action}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortAndFilterProcesses(
                      inventory.processes,
                      processSearch,
                      processSort.column,
                      processSort.direction
                    ).map((proc) => {
                      const isIdle = proc.pid === IDLE_PROCESS_PID;
                      return (
                        <tr key={proc.pid} className={isIdle ? styles.idleRow : undefined}>
                          <td className={styles.mono}>{proc.pid}</td>
                          <td>
                            {isIdle ? (
                              <span className={styles.idleLabel}>
                                {proc.name} · {d.processes.idle}
                              </span>
                            ) : (
                              proc.name
                            )}
                          </td>
                          <td>{proc.cpu_percent != null ? proc.cpu_percent.toFixed(1) : "-"}</td>
                          <td>{proc.memory_percent != null ? proc.memory_percent.toFixed(1) : "-"}</td>
                          <td>{proc.username ?? "-"}</td>
                          <td>{proc.status ?? "-"}</td>
                          <td>
                            <button
                              type="button"
                              className={styles.actionButtonDanger}
                              onClick={() =>
                                setPendingAction({
                                  commandType: "kill_process",
                                  action: "kill",
                                  target: String(proc.pid),
                                  label: proc.name,
                                })
                              }
                            >
                              {d.processes.kill}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className={styles.noData}>{d.processes.noData}</p>
          )}
        </div>
      )}

      {activeTab === "services" && (
        <div>
          {inventory && inventory.services.length > 0 ? (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>{d.services.name}</th>
                    <th>{d.services.state}</th>
                    <th>{d.services.startupType}</th>
                    <th>{d.services.action}</th>
                  </tr>
                </thead>
                <tbody>
                  {inventory.services.map((svc) => {
                    const stateLower = (svc.state ?? "").toLowerCase();
                    const isRunning = stateLower.includes("running") || stateLower.includes("active");
                    const isStopped =
                      stateLower.includes("stop") || stateLower.includes("inactive") || stateLower.includes("dead");
                    const requestService = (action: "start" | "stop" | "restart") =>
                      setPendingAction({
                        commandType: "service_control",
                        action,
                        target: svc.name,
                        label: svc.display_name ?? svc.name,
                      });
                    return (
                      <tr key={svc.name}>
                        <td>{svc.display_name ?? svc.name}</td>
                        <td>{svc.state ?? "-"}</td>
                        <td>{svc.startup_type ?? "-"}</td>
                        <td className={styles.actionCell}>
                          <button
                            type="button"
                            className={styles.actionButton}
                            disabled={isRunning}
                            onClick={() => requestService("start")}
                          >
                            {d.services.start}
                          </button>
                          <button
                            type="button"
                            className={styles.actionButtonDanger}
                            disabled={isStopped}
                            onClick={() => requestService("stop")}
                          >
                            {d.services.stop}
                          </button>
                          <button type="button" className={styles.actionButton} onClick={() => requestService("restart")}>
                            {d.services.restart}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className={styles.noData}>{d.services.noData}</p>
          )}
        </div>
      )}

      {activeTab === "sessions" && (
        <div>
          {telemetry && telemetry.sessions.length > 0 ? (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>{d.sessions.username}</th>
                    <th>{d.sessions.sessionName}</th>
                    <th>{d.sessions.status}</th>
                    <th>{d.sessions.logonTime}</th>
                  </tr>
                </thead>
                <tbody>
                  {telemetry.sessions.map((session, idx) => (
                    <tr key={`${session.username}-${session.session_name ?? idx}`}>
                      <td>{session.username}</td>
                      <td>{session.session_name ?? "-"}</td>
                      <td>
                        {session.status === "active"
                          ? d.sessions.statusActive
                          : session.status === "disconnected"
                            ? d.sessions.statusDisconnected
                            : (session.status ?? "-")}
                      </td>
                      <td>{session.logon_time ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className={styles.noData}>{d.sessions.noData}</p>
          )}
        </div>
      )}

      {pendingAction && (
        <ConfirmModal
          title={cmdText.confirmTitle}
          message={
            pendingAction.commandType === "kill_process"
              ? cmdText.confirmKillProcess(pendingAction.target)
              : pendingAction.commandType === "power_control"
                ? cmdText.confirmPower(
                    agent.hostname,
                    pendingAction.action === "reboot"
                      ? cmdText.actionReboot
                      : pendingAction.action === "shutdown"
                        ? cmdText.actionShutdown
                        : cmdText.actionLogoff
                  )
                : cmdText.confirmServiceControl(
                    pendingAction.label,
                    pendingAction.action === "start"
                      ? cmdText.actionStart
                      : pendingAction.action === "stop"
                        ? cmdText.actionStop
                        : cmdText.actionRestart
                  )
          }
          confirmLabel={cmdText.confirmButton}
          cancelLabel={cmdText.cancelButton}
          busy={submitting}
          busyLabel={cmdText.processing}
          onConfirm={handleConfirmAction}
          onCancel={() => setPendingAction(null)}
        />
      )}
      <ToastStack toasts={toasts} onDismiss={dismissToast} />
    </section>
  );
}
