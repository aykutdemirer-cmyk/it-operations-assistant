const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type HealthResponse = {
  status: string;
};

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_URL}/api/health`);

  if (!response.ok) {
    throw new Error(`Backend health check failed: ${response.status}`);
  }

  return response.json();
}

export async function fetchHealthDb(): Promise<{ database: string }> {
  const response = await fetch(`${API_URL}/api/health/db`);

  if (!response.ok) {
    throw new Error(`Database health check failed: ${response.status}`);
  }

  return response.json();
}

export async function fetchHealthSnmp(): Promise<{ snmp: string }> {
  const response = await fetch(`${API_URL}/api/health/snmp`);

  if (!response.ok) {
    throw new Error(`SNMP health check failed: ${response.status}`);
  }

  return response.json();
}

export type PortResult = {
  port: number;
  status: "open" | "closed" | "timeout";
  latency_ms: number | null;
};

export type DeviceType =
  | "firewall"
  | "router"
  | "switch"
  | "server"
  | "workstation"
  | "printer"
  | "access_point"
  | "camera"
  | "nas"
  | "network_device"
  | "unknown";

export type PingResult = {
  ip: string;
  status: "up" | "down";
  latency_ms: number | null;
  mac_address: string | null;
  vendor: string | null;
  hostname: string | null;
  open_ports: PortResult[];
  device_type: DeviceType;
  confidence: "high" | "medium" | "low";
  evidence: string[];
};

export type ScanResult = {
  cidr: string;
  total_hosts: number;
  alive_hosts: number;
  hosts: PingResult[];
};

export async function scanNetwork(cidr: string): Promise<ScanResult> {
  const response = await fetch(`${API_URL}/api/discovery/icmp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cidr }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Tarama başarısız: ${response.status}`);
  }

  return response.json();
}

export type Asset = {
  id: string;
  ip_address: string;
  hostname: string | null;
  mac_address: string | null;
  vendor: string | null;
  device_type: DeviceType;
  confidence: "high" | "medium" | "low";
  evidence: string[];
  open_ports: PortResult[];
  status: string;
  latency_ms: number | null;
  last_seen: string;
  created_at: string;
  updated_at: string;
};

export async function fetchAssets(): Promise<Asset[]> {
  const response = await fetch(`${API_URL}/api/assets`);

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object"
          ? Object.values(detail).join(", ")
          : `Asset listesi alınamadı: ${response.status}`;
    throw new Error(message);
  }

  return response.json();
}

export type ScanStatus = "running" | "completed" | "failed";

export type Scan = {
  id: string;
  cidr: string;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  hosts_scanned: number;
  hosts_discovered: number;
  open_ports: number;
  status: ScanStatus;
};

// `apps/api/app/snmp/models.py` ile birebir aynı sözleşme (Faz 26 —
// `computeAlerts`'in SNMP-tabanlı kurallarının girdisi; Faz 27 —
// `fetchMonitoring()`'in dönüş tipi).
export type SnmpIfStatus =
  | "up"
  | "down"
  | "testing"
  | "unknown"
  | "dormant"
  | "notPresent"
  | "lowerLayerDown";

export type SnmpInterfaceInfo = {
  if_index: number;
  if_name: string | null;
  if_descr: string | null;
  if_admin_status: SnmpIfStatus | null;
  if_oper_status: SnmpIfStatus | null;
  if_speed_bps: number | null;
  if_in_octets: number | null;
  if_out_octets: number | null;
  if_counters_64bit: boolean | null;
  if_in_bps: number | null;
  if_out_bps: number | null;
  if_in_errors: number | null;
  if_out_errors: number | null;
};

export type SnmpSystemInfo = {
  sys_name: string | null;
  sys_descr: string | null;
  sys_object_id: string | null;
  sys_uptime_ticks: number | null;
};

export type SnmpPollStatus =
  | "not_configured"
  | "unreachable"
  | "timeout"
  | "authentication_failed"
  | "success"
  | "partial";

export type SnmpPollResult = {
  asset_id: string;
  polled_at: string;
  status: SnmpPollStatus;
  system: SnmpSystemInfo | null;
  interfaces: SnmpInterfaceInfo[];
  error: string | null;
  duration_ms: number | null;
};

// `apps/api/app/snmp/poller.py::PollBatchResult` ile birebir (Faz 24).
export type PollBatchResult = {
  started_at: string;
  completed_at: string;
  duration_ms: number;
  total: number;
  polled: number;
  not_configured: number;
  results: SnmpPollResult[];
};

export async function pollAssetSnmp(assetId: string): Promise<SnmpPollResult> {
  const response = await fetch(`${API_URL}/api/snmp/poll/${assetId}`, { method: "POST" });
  if (!response.ok) {
    await throwApiError(response, "SNMP poll başarısız");
  }
  return response.json();
}

export async function fetchMonitoring(): Promise<PollBatchResult> {
  const response = await fetch(`${API_URL}/api/monitoring`);

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object"
          ? Object.values(detail).join(", ")
          : `İzleme verisi alınamadı: ${response.status}`;
    throw new Error(message);
  }

  return response.json();
}

export async function fetchScans(): Promise<Scan[]> {
  const response = await fetch(`${API_URL}/api/scans`);

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object"
          ? Object.values(detail).join(", ")
          : `Scan listesi alınamadı: ${response.status}`;
    throw new Error(message);
  }

  return response.json();
}

// `status` sayesinde çağıran taraf (ör. 409 "profile has assignments")
// mesaj metnini parse etmeden ayırt edebilir.
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function extractErrorMessage(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") return Object.values(detail).join(", ");
  return `${fallback}: ${response.status}`;
}

async function throwApiError(response: Response, fallback: string): Promise<never> {
  throw new ApiError(await extractErrorMessage(response, fallback), response.status);
}

// `apps/api/app/agents/models.py::AgentSummary` ile birebir (Faz 28) —
// yalnızca `/settings`'in Agent Configuration bölümündeki gerçek sayaç
// için kullanılıyor; tam `/agents` sayfası henüz yok (Faz 33+).
export type AgentOS = "windows" | "linux";
export type AgentStatus = "online" | "offline" | "unknown";

export type AgentSummary = {
  id: string;
  hostname: string;
  os: AgentOS;
  os_version: string | null;
  agent_version: string;
  local_ip: string | null;
  asset_id: string | null;
  status: AgentStatus;
  registered_at: string;
  last_heartbeat_at: string | null;
};

export async function fetchAgents(): Promise<AgentSummary[]> {
  const response = await fetch(`${API_URL}/api/agents`);
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "Agent listesi alınamadı"));
  }
  return response.json();
}

// `apps/api/app/agents/models.py::EnrollmentCodeResponse`/
// `EnrollmentCodeSummary` ile birebir (Faz 31). Kod bir credential
// DEĞİLDİR — tek başına hiçbir kaynağa erişim vermez, yalnızca "bu
// kaydı bir insan başlattı" onayıdır; bu yüzden plaintext taşınması
// (SNMP community/agent token'ın aksine) güvenlik ilkesini ihlal etmez.
export type EnrollmentCode = {
  code: string;
  expires_at: string;
};

export type EnrollmentCodeSummary = EnrollmentCode & {
  created_at: string;
};

export async function createEnrollmentCode(): Promise<EnrollmentCode> {
  const response = await fetch(`${API_URL}/api/agents/enrollment-codes`, { method: "POST" });
  if (!response.ok) {
    await throwApiError(response, "Enrollment kodu üretilemedi");
  }
  return response.json();
}

export async function fetchEnrollmentCodes(): Promise<EnrollmentCodeSummary[]> {
  const response = await fetch(`${API_URL}/api/agents/enrollment-codes`);
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "Enrollment kodları alınamadı"));
  }
  return response.json();
}

// `apps/api/app/agents/models.py::WindowsAgentDownloadInfo` ile birebir
// (Faz 32). `available=false` ise diğer alanlar `null` — hiçbir zaman
// uydurma bir versiyon/boyut gösterilmez.
export type WindowsAgentDownloadInfo = {
  available: boolean;
  version: string | null;
  filename: string | null;
  size_bytes: number | null;
  built_at: string | null;
};

export async function fetchWindowsAgentDownloadInfo(): Promise<WindowsAgentDownloadInfo> {
  const response = await fetch(`${API_URL}/api/agents/download/windows/info`);
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "İndirme bilgisi alınamadı"));
  }
  return response.json();
}

// Gerçek dosya indirmesi tarayıcının kendi native davranışına
// bırakılır — bu yalnızca tam URL'i döner, `SendUserFile`/fetch ile
// içeriği kendimiz çekip bir `<a download>` linki OLUŞTURMAYIZ (bkz.
// AgentDownloadPanel.tsx — düz bir `<a href=...>` kullanılıyor).
export function windowsAgentDownloadUrl(): string {
  return `${API_URL}/api/agents/download/windows`;
}

// `apps/api/app/agents/models.py` ile birebir (Faz 30). `token`/
// `token_hash` hiçbir response'ta ASLA yer almaz.
export type AgentDiskSample = {
  device: string;
  total_bytes: number | null;
  used_bytes: number | null;
  free_bytes: number | null;
  percent: number | null;
};

export type AgentNetworkInterfaceSample = {
  name: string;
  ip_address: string | null;
  addresses: string[];
  interface_type: string | null;
  mac_address: string | null;
  speed_bps: number | null;
  state: string | null;
  rx_bytes: number | null;
  tx_bytes: number | null;
  rx_errors: number | null;
  tx_errors: number | null;
};

// Faz 34 — User Sessions Tracking. `apps/api/app/agents/models.py::
// SessionInfo` ile birebir.
export type AgentSessionInfo = {
  username: string;
  session_name: string | null;
  status: string | null;
  logon_time: string | null;
};

export type AgentTelemetry = {
  collected_at: string;
  schema_version: number;
  cpu_percent: number | null;
  memory_total_bytes: number | null;
  memory_used_bytes: number | null;
  memory_percent: number | null;
  disks: AgentDiskSample[];
  network_interfaces: AgentNetworkInterfaceSample[];
  sessions: AgentSessionInfo[];
  last_logged_in_user: string | null;
  active_sessions_count: number | null;
};

export type AgentHardwareInfo = {
  manufacturer: string | null;
  model: string | null;
  cpu_model: string | null;
  cpu_cores: number | null;
  cpu_logical_processors: number | null;
  total_memory_bytes: number | null;
};

export type AgentOSInfo = {
  name: string | null;
  version: string | null;
  kernel: string | null;
  architecture: string | null;
  boot_time: string | null;
};

export type AgentSoftwareItem = { name: string; version: string | null };
export type AgentServiceInfo = {
  name: string;
  display_name: string | null;
  state: string | null;
  startup_type: string | null;
};
export type AgentProcessInfo = {
  pid: number;
  name: string;
  cpu_percent: number | null;
  memory_percent: number | null;
  username: string | null;
  status: string | null;
};

export type AgentInventory = {
  collected_at: string;
  schema_version: number;
  hardware: AgentHardwareInfo | null;
  os: AgentOSInfo | null;
  network_interfaces: AgentNetworkInterfaceSample[];
  software: AgentSoftwareItem[];
  services: AgentServiceInfo[];
  processes: AgentProcessInfo[];
};

export type AgentDetail = AgentSummary & {
  fqdn: string | null;
  architecture: string | null;
  local_ip: string | null;
  mac_address: string | null;
  capabilities: string[];
  revoked_at: string | null;
  latest_telemetry: AgentTelemetry | null;
  inventory: AgentInventory | null;
};

export async function fetchAgent(agentId: string): Promise<AgentDetail> {
  const response = await fetch(`${API_URL}/api/agents/${agentId}`);
  if (!response.ok) {
    await throwApiError(response, "Agent detayı alınamadı");
  }
  return response.json();
}

// Faz 34 — Hızlı Bağlantı. RDP: gerçek bir `<a href>` indirme linki
// (backend `.rdp` dosyası üretir, tarayıcı/işletim sistemi onu açar —
// bkz. `apps/api/app/agents/rdp.py`). Bağlantıyı frontend KURMAZ,
// yalnızca dosyanın URL'sini oluşturur.
export function agentRdpConnectUrl(agentId: string): string {
  return `${API_URL}/api/agents/${agentId}/connect/rdp`;
}

// Faz 37 — Wake-on-LAN. Agent'ın KENDİSİYLE hiç konuşmaz — cihaz
// Çevrimdışı iken de çağrılabilir (WoL'un bütün amacı bu).
export async function wakeAgent(agentId: string): Promise<{ status: string; mac_address: string }> {
  const response = await fetch(`${API_URL}/api/agents/${agentId}/wake`, { method: "POST" });
  if (!response.ok) {
    await throwApiError(response, "Wake-on-LAN paketi gönderilemedi");
  }
  return response.json();
}

// Kendi yerel SSH istemcisini kullanmak isteyenler için — `local_ip`/
// kullanıcı adı zaten `GET /api/agents/{id}` yanıtında var, komut/URI
// istemci tarafında üretilir.
export function agentSshCommand(localIp: string, username: string | null): string {
  return username ? `ssh ${username}@${localIp}` : `ssh ${localIp}`;
}

export function agentSshUri(localIp: string, username: string | null): string {
  return username ? `ssh://${username}@${localIp}` : `ssh://${localIp}`;
}

// Faz 35 — Web SSH Terminal. `WS /api/agents/{id}/ssh` — kimlik bilgisi
// bu WebSocket'in İLK mesajıyla gönderilir, backend'de HİÇBİR ZAMAN
// saklanmaz (bkz. `apps/api/app/agents/ssh_proxy.py`).
export function agentSshWebSocketUrl(agentId: string): string {
  const wsBase = API_URL.replace(/^https:/, "wss:").replace(/^http:/, "ws:");
  return `${wsBase}/api/agents/${agentId}/ssh`;
}

// `apps/api/app/agents/command_models.py` ile birebir (Faz 33 — Remote
// Command Execution). Komut ANINDA çalışmaz — `pending` olarak
// oluşturulur, Agent'ın command-poll döngüsü çekip çalıştırır ve
// gerçek sonucu bildirir (bkz. `pollAgentCommand`, kısa client-side
// polling ile terminal duruma kadar beklenir).
export type AgentCommandType = "kill_process" | "service_control" | "refresh_inventory" | "power_control";
export type AgentCommandAction = "kill" | "start" | "stop" | "restart" | "collect" | "reboot" | "shutdown" | "logoff";
export type AgentCommandStatus = "pending" | "sent" | "succeeded" | "failed" | "rejected";

export type AgentCommand = {
  id: string;
  agent_id: string;
  command_type: AgentCommandType;
  action: AgentCommandAction;
  target: string;
  status: AgentCommandStatus;
  result_detail: string | null;
  requested_by: string | null;
  created_at: string;
  sent_at: string | null;
  completed_at: string | null;
};

export async function submitAgentCommand(
  agentId: string,
  body: { command_type: AgentCommandType; action: AgentCommandAction; target: string }
): Promise<AgentCommand> {
  const response = await fetch(`${API_URL}/api/agents/${agentId}/commands`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    await throwApiError(response, "Komut oluşturulamadı");
  }
  return response.json();
}

const _TERMINAL_STATUSES: AgentCommandStatus[] = ["succeeded", "failed", "rejected"];

/** Bir komut `pending`/`sent` iken kısa aralıklarla `GET .../commands`ı
 * yoklayıp terminal bir duruma (succeeded/failed/rejected) ulaşmasını
 * bekler — Agent'ın gerçek yürütmesi asenkron olduğu için (command-poll
 * aralığı kadar gecikebilir). `maxWaitMs` dolarsa son bilinen durumla
 * (muhtemelen hâlâ `pending`) döner, hata FIRLATMAZ — çağıran taraf
 * "hâlâ işleniyor" durumunu kendi UI'ında gösterebilir. */
export async function pollAgentCommand(
  agentId: string,
  commandId: string,
  { intervalMs = 1500, maxWaitMs = 15000 }: { intervalMs?: number; maxWaitMs?: number } = {}
): Promise<AgentCommand | null> {
  const deadline = Date.now() + maxWaitMs;
  let lastKnown: AgentCommand | null = null;
  while (Date.now() < deadline) {
    const history = await fetchAgentCommands(agentId);
    const current = history.find((c) => c.id === commandId) ?? null;
    if (current) {
      lastKnown = current;
      if (_TERMINAL_STATUSES.includes(current.status)) {
        return current;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  return lastKnown;
}

export async function fetchAgentCommands(agentId: string): Promise<AgentCommand[]> {
  const response = await fetch(`${API_URL}/api/agents/${agentId}/commands`);
  if (!response.ok) {
    await throwApiError(response, "Komut geçmişi alınamadı");
  }
  return response.json();
}

// `apps/api/app/snmp/profile_config.py::SNMPProfileResponse` ile
// birebir (Faz 29). `*_ref` alanları yalnızca birer İSİM (env değişken
// adı) — gerçek secret DEĞERİ backend'den asla dönmez.
export type SnmpProfileVersion = "v2c" | "v3";
export type SnmpAuthProtocol = "MD5" | "SHA" | "SHA224" | "SHA256" | "SHA384" | "SHA512";
export type SnmpPrivProtocol = "DES" | "AES" | "AES192" | "AES256";
export type SnmpSecurityLevel = "noAuthNoPriv" | "authNoPriv" | "authPriv";
export type SnmpProfileStatus = "ready" | "not_configured" | "disabled";

export type SnmpProfile = {
  id: string;
  name: string;
  target_host: string;
  port: number;
  version: SnmpProfileVersion;
  timeout_seconds: number;
  retries: number;
  enabled: boolean;
  credential_configured: boolean;
  status: SnmpProfileStatus;
  security_level: SnmpSecurityLevel | null;
  // Faz 29.5 — bu profile `asset_snmp_profiles` üzerinden atanmış asset
  // sayısı (Settings UI'daki "Assigned Devices" sütunu).
  assigned_asset_count: number;
  community_ref: string | null;
  username: string | null;
  auth_protocol: SnmpAuthProtocol | null;
  auth_credential_ref: string | null;
  priv_protocol: SnmpPrivProtocol | null;
  priv_credential_ref: string | null;
  created_at: string;
  updated_at: string;
};

export type SnmpProfileWrite = {
  name: string;
  target_host: string;
  port: number;
  version: SnmpProfileVersion;
  timeout_seconds: number;
  retries: number;
  enabled: boolean;
  community_ref: string | null;
  username: string | null;
  auth_protocol: SnmpAuthProtocol | null;
  auth_credential_ref: string | null;
  priv_protocol: SnmpPrivProtocol | null;
  priv_credential_ref: string | null;
};

export type SnmpTestStatus =
  | "connected"
  | "timeout"
  | "authentication_failed"
  | "unreachable"
  | "not_configured"
  | "error";

export type SnmpTestConnectionResult = {
  status: SnmpTestStatus;
  message: string;
  sys_name: string | null;
  sys_descr: string | null;
  sys_object_id: string | null;
  sys_uptime_ticks: number | null;
};

export async function fetchSnmpProfiles(): Promise<SnmpProfile[]> {
  const response = await fetch(`${API_URL}/api/snmp/profiles`);
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "SNMP profilleri alınamadı"));
  }
  return response.json();
}

export async function createSnmpProfile(payload: SnmpProfileWrite): Promise<SnmpProfile> {
  const response = await fetch(`${API_URL}/api/snmp/profiles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "SNMP profili oluşturulamadı"));
  }
  return response.json();
}

export async function updateSnmpProfile(id: string, payload: SnmpProfileWrite): Promise<SnmpProfile> {
  const response = await fetch(`${API_URL}/api/snmp/profiles/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "SNMP profili güncellenemedi"));
  }
  return response.json();
}

export async function deleteSnmpProfile(id: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/snmp/profiles/${id}`, { method: "DELETE" });
  if (!response.ok && response.status !== 204) {
    await throwApiError(response, "SNMP profili silinemedi");
  }
}

export async function testSnmpProfileConnection(id: string): Promise<SnmpTestConnectionResult> {
  const response = await fetch(`${API_URL}/api/snmp/profiles/${id}/test`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "Bağlantı testi başarısız"));
  }
  return response.json();
}

// `apps/api/app/snmp/asset_profile_service.py::AssetSnmpProfileResponse`/
// `AssetSummary` ile birebir (Faz 29.5) — Asset ↔ SNMP Profile ilişkisi.
export type AssetSnmpProfileResponse = {
  configured: boolean;
  profile: SnmpProfile | null;
  target_host_matches_asset: boolean | null;
};

export type SnmpProfileAssetSummary = {
  id: string;
  ip_address: string;
  hostname: string | null;
  device_type: DeviceType;
  status: string;
};

export async function fetchAssetSnmpProfile(assetId: string): Promise<AssetSnmpProfileResponse> {
  const response = await fetch(`${API_URL}/api/assets/${assetId}/snmp-profile`);
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "Asset SNMP profili alınamadı"));
  }
  return response.json();
}

export async function assignSnmpProfileToAsset(assetId: string, profileId: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/assets/${assetId}/snmp-profile/${profileId}`, {
    method: "PUT",
  });
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "SNMP profili atanamadı"));
  }
}

export async function unassignSnmpProfileFromAsset(assetId: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/assets/${assetId}/snmp-profile`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "SNMP profili kaldırılamadı"));
  }
}

export async function fetchAssetsForSnmpProfile(profileId: string): Promise<SnmpProfileAssetSummary[]> {
  const response = await fetch(`${API_URL}/api/snmp/profiles/${profileId}/assets`);
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "Profile atanmış asset'ler alınamadı"));
  }
  return response.json();
}
