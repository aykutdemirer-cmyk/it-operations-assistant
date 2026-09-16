import type { Permission } from "@/lib/auth/permissions";

// `NEXT_PUBLIC_API_URL` açıkça set edilmediği sürece MUTLAK bir host
// (ör. "http://localhost:8000") DEĞİL, göreli bir yol kullanılır —
// böylece istek her zaman sayfanın kendi origin'ine gider ve
// `next.config.ts::rewrites()` bunu sunucu tarafında gerçek backend'e
// proxy'ler. Tarayıcı `http://10.0.213.30:3000` üzerinden açıldığında
// eski mutlak "http://localhost:8000" değeri KULLANICININ KENDİ
// makinesini hedefliyordu (backend sunucusunu değil) — "Backend:
// Kontrol ediliyor..." durumunda sonsuza kadar takılı kalmanın kök
// nedeni buydu.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

// Yalnızca SSH WebSocket için: `next.config.ts::rewrites()` bir HTTP
// GET/POST proxy'sidir, WebSocket upgrade isteklerini güvenilir şekilde
// PROXY'LEMEZ — bu yüzden SSH bağlantısı backend'e DOĞRUDAN gider.
// Sayfa hangi hostname üzerinden açıldıysa (LAN IP dahil) o hostname'in
// backend portu (8000) kullanılır. ÖNEMLİ: bu, backend'in yalnızca
// `127.0.0.1` DEĞİL, o LAN arayüzünde de dinliyor olmasını gerektirir
// (`.claude/launch.json`'daki `--host` — bilinçli bir güvenlik kararı,
// Auth/RBAC henüz olmadığı için varsayılan olarak GENİŞLETİLMEDİ).
function backendOrigin(): string {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "http://localhost:8000";
}

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
  // HOST-RESOURCES-MIB — çoğu switch/router/firewall desteklemez, bu
  // durumda dürüstçe `null` (bkz. app/snmp/oid_map.py).
  cpu_percent: number | null;
  memory_used_bytes: number | null;
  memory_total_bytes: number | null;
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

// `apps/api/app/snmp/monitoring_cache.py` ile birebir. Arka plan SNMP
// polling worker'ının (bkz. `app/snmp/scheduler.py`) periyodik olarak
// topladığı, süreç-içi (kalıcı olmayan) telemetri önbelleği.
export type PollLogEntry = {
  asset_id: string;
  status: SnmpPollStatus;
  duration_ms: number | null;
  oid_count: number;
  polled_at: string;
  error: string | null;
};

export type BandwidthSample = {
  ts: string;
  total_in_bps: number | null;
  total_out_bps: number | null;
};

export type MonitoringHistoryResponse = {
  latest_batch: PollBatchResult | null;
  poll_log: PollLogEntry[];
  bandwidth_history: BandwidthSample[];
};

// `GET /api/monitoring`'in AKSİNE yeni bir poll turu TETİKLEMEZ —
// yalnızca arka plan worker'ının zaten topladığı veriyi okur, bu yüzden
// sık (ör. 5-10sn) çağrılması güvenlidir (bkz. `AutoRefresh` deseni).
export async function fetchMonitoringHistory(): Promise<MonitoringHistoryResponse> {
  const response = await fetch(`${API_URL}/api/monitoring/history`);
  if (!response.ok) {
    await throwApiError(response, "İzleme geçmişi alınamadı");
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

// ============================================================
// Faz 71 — Zamanlanmış Ağ Taraması (Ayarlar > Zamanlanmış Taramalar).
// `apps/api/app/routes/discovery.py` ile birebir. `require_role("ADMIN")`
// — elle taramadan (`/icmp`) farklı olarak auth header gerektirir.
// ============================================================

export type ScheduledScan = {
  id: string;
  cidr: string;
  interval_hours: number;
  enabled: boolean;
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_error: string | null;
  created_at: string;
  updated_at: string;
};

export type ScheduledScanRequest = {
  cidr?: string;
  interval_hours?: number;
  enabled?: boolean;
};

export async function fetchScheduledScans(token: string): Promise<ScheduledScan[]> {
  const response = await fetch(`${API_URL}/api/discovery/schedules`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Zamanlanmış taramalar alınamadı");
  return response.json();
}

export async function createScheduledScan(token: string, payload: Required<ScheduledScanRequest>): Promise<ScheduledScan> {
  const response = await fetch(`${API_URL}/api/discovery/schedules`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "Zamanlanmış tarama oluşturulamadı");
  return response.json();
}

export async function updateScheduledScan(
  token: string,
  id: string,
  payload: ScheduledScanRequest,
): Promise<ScheduledScan> {
  const response = await fetch(`${API_URL}/api/discovery/schedules/${id}`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "Zamanlanmış tarama güncellenemedi");
  return response.json();
}

export async function deleteScheduledScan(token: string, id: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/discovery/schedules/${id}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!response.ok) await throwApiError(response, "Zamanlanmış tarama silinemedi");
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

// FastAPI/Pydantic 422 doğrulama hatalarında `detail` bir DİZİDİR
// (`[{"loc": [...], "msg": "...", "type": "..."}]`) — düz bir obje
// DEĞİL. Önceki kod `typeof detail === "object"` kontrolüyle diziyi de
// yakalayıp `Object.values(detail).join(", ")` çağırıyordu; bir dizinin
// elemanları (obje) `join()` içinde `toString()`'e düşüp gerçek, canlı
// bir bug olarak "[object Object]" gösteriyordu — HER 422 hatasını
// etkiliyordu, yalnızca LDAP'a özgü değildi.
function _validationErrorItemToText(item: unknown): string {
  if (typeof item === "string") return item;
  if (item && typeof item === "object" && "msg" in item) {
    const record = item as { msg: unknown; loc?: unknown };
    const loc = Array.isArray(record.loc) ? record.loc.filter((p) => p !== "body").join(".") : undefined;
    return loc ? `${loc}: ${record.msg}` : String(record.msg);
  }
  return JSON.stringify(item);
}

async function extractErrorMessage(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(_validationErrorItemToText).join("; ");
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
  // Lifecycle Management — Uzaktan Sürüm Güncelleme. Sunucuda gerçekten
  // build edilmiş bir paket yoksa (ör. Linux, ya da henüz build
  // edilmemiş Windows) her ikisi de dürüstçe `false`/`null`.
  update_available: boolean;
  latest_available_version: string | null;
};

export async function fetchAgents(): Promise<AgentSummary[]> {
  const response = await fetch(`${API_URL}/api/agents`);
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "Agent listesi alınamadı"));
  }
  return response.json();
}

// Lifecycle Management — Silme (soft-delete/arşivleme), Geri Yükleme,
// Otomatik Temizleme Politikası, Uzaktan Sürüm Güncelleme.
// `apps/api/app/agents/models.py` ile birebir.
export type ArchivedReason = "manual" | "inactivity";

export type ArchivedAgentSummary = {
  id: string;
  hostname: string;
  os: AgentOS;
  os_version: string | null;
  local_ip: string | null;
  registered_at: string;
  last_heartbeat_at: string | null;
  archived_at: string;
  archived_reason: ArchivedReason;
  archived_after_inactive_days: number | null;
  active_duration_seconds: number | null;
};

export type AgentDeleteResult = {
  archived: boolean;
  uninstall_command_id: string | null;
};

export type AgentRetentionPolicy = {
  enabled: boolean;
  retention_days: number;
};

export async function deleteAgent(
  agentId: string,
  sendUninstallCommand: boolean
): Promise<AgentDeleteResult> {
  const response = await fetch(
    `${API_URL}/api/agents/${agentId}?send_uninstall_command=${sendUninstallCommand}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    await throwApiError(response, "Agent silinemedi");
  }
  return response.json();
}

export async function restoreAgent(agentId: string): Promise<AgentSummary> {
  const response = await fetch(`${API_URL}/api/agents/${agentId}/restore`, { method: "POST" });
  if (!response.ok) {
    await throwApiError(response, "Agent geri yüklenemedi");
  }
  return response.json();
}

export async function fetchArchivedAgents(): Promise<ArchivedAgentSummary[]> {
  const response = await fetch(`${API_URL}/api/agents/archived`);
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "Arşivlenen agent'lar alınamadı"));
  }
  return response.json();
}

export async function fetchRetentionPolicy(): Promise<AgentRetentionPolicy> {
  const response = await fetch(`${API_URL}/api/agents/retention-policy`);
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "Temizleme politikası alınamadı"));
  }
  return response.json();
}

export async function updateRetentionPolicy(
  policy: AgentRetentionPolicy
): Promise<AgentRetentionPolicy> {
  const response = await fetch(`${API_URL}/api/agents/retention-policy`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(policy),
  });
  if (!response.ok) {
    await throwApiError(response, "Temizleme politikası güncellenemedi");
  }
  return response.json();
}

export async function triggerAgentUpdate(agentId: string): Promise<{ status: string; command_id: string }> {
  const response = await fetch(`${API_URL}/api/agents/${agentId}/update`, { method: "POST" });
  if (!response.ok) {
    await throwApiError(response, "Güncelleme komutu gönderilemedi");
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
  // Düz bir GET/dosya indirme — `next.config.ts::rewrites()`'in genel
  // `/api/:path*` proxy'si üzerinden geçer, `backendOrigin()`'e (backend
  // portunun DIŞARIDAN da açık olmasını gerektirir) ihtiyaç yok.
  return `${API_URL}/api/agents/download/windows`;
}

// Faz: Windows Servisi paketi — başka bir bilgisayara kalıcı bir
// servis olarak kurmak için (`itops-agent.exe` + `install_windows_
// service.ps1` + `uninstall_windows_service.ps1` + README.txt, TEK
// bir ZIP). `WindowsAgentDownloadInfo` ile AYNI sözleşme, ayrı artifact
// (bkz. app/agents/download.py::resolve_windows_service_artifact).
export async function fetchWindowsServiceDownloadInfo(): Promise<WindowsAgentDownloadInfo> {
  const response = await fetch(`${API_URL}/api/agents/download/windows-service/info`);
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "İndirme bilgisi alınamadı"));
  }
  return response.json();
}

export function windowsServiceDownloadUrl(): string {
  return `${API_URL}/api/agents/download/windows-service`;
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

// Windows Update Tarama Motoru — `apps/api/app/agents/update_models.py`
// ile birebir. `scan_method` İKİ FARKLI anlam taşıyabilir: `com`
// GERÇEKTEN BEKLEYEN güncellemeleri, `installed_hotfixes` (COM
// başarısız olduğunda devreye giren yedek) ZATEN KURULMUŞ hotfix'leri
// döner — frontend bu ikisini ASLA aynıymış gibi GÖSTERMEMELİ.
export type WindowsUpdateScanMethod = "com" | "installed_hotfixes" | "unavailable";

export type WindowsUpdateItem = {
  kb_number: string | null;
  title: string;
  description: string | null;
  size_bytes: number | null;
};

export type AgentWindowsUpdates = {
  agent_id: string;
  collected_at: string;
  scan_method: WindowsUpdateScanMethod;
  is_admin: boolean;
  updates: WindowsUpdateItem[];
  error: string | null;
  // `Microsoft.Update.SystemInfo().RebootRequired` — HER taramada taze
  // sorgulanan, makine genelindeki bekleyen yeniden başlatma durumu.
  reboot_required: boolean;
};

export async function fetchAgentWindowsUpdates(agentId: string): Promise<AgentWindowsUpdates | null> {
  const response = await fetch(`${API_URL}/api/agents/${agentId}/updates`);
  if (response.status === 404) {
    // Bu agent hiç tarama göndermemiş (Linux agent'ı, ya da Windows
    // agent'ı henüz ilk taramasını yapmamış) — dürüstçe `null`, hata
    // FIRLATILMAZ (çağıran taraf "henüz taranmadı" boş durumunu gösterir).
    return null;
  }
  if (!response.ok) {
    await throwApiError(response, "Windows Update taraması alınamadı");
  }
  return response.json();
}

// Bir KB numarasını (ör. `"KB5001234"`, birden fazla KB'yi virgülle
// ayrılmış olarak taşıyabilir — bkz. `WindowsUpdateItem.kb_number`)
// resmi Microsoft Support arama sayfasına bağlar. Yalnızca İLK KB
// numarası kullanılır (çoklu-KB durumları nadir, kullanıcıya en
// azından bir başlangıç noktası vermek yeterli). Sayı DIŞINDAKİ
// karakterler ("KB" öneki dahil) URL'in path segmentine dahil
// EDİLMEZ — support.microsoft.com yalnızca ham sayıyı bekler.
export function windowsUpdateKbSupportUrl(kbNumber: string): string | null {
  const firstKb = kbNumber.split(",")[0]?.trim() ?? "";
  const digitsOnly = firstKb.replace(/^KB/i, "").trim();
  if (!digitsOnly) return null;
  return `https://support.microsoft.com/help/${digitsOnly}`;
}

// Faz 34 — Hızlı Bağlantı. RDP: gerçek bir `<a href>` indirme linki
// (backend `.rdp` dosyası üretir, tarayıcı/işletim sistemi onu açar —
// bkz. `apps/api/app/agents/rdp.py`). Bağlantıyı frontend KURMAZ,
// yalnızca dosyanın URL'sini oluşturur.
export function agentRdpConnectUrl(agentId: string): string {
  // Düz bir GET/dosya indirme — `windowsAgentDownloadUrl` ile aynı
  // gerekçeyle proxy üzerinden gider, doğrudan backend origin'i gerekmez.
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
  const wsBase = backendOrigin().replace(/^https:/, "wss:").replace(/^http:/, "ws:");
  return `${wsBase}/api/agents/${agentId}/ssh`;
}

// `apps/api/app/agents/command_models.py` ile birebir (Faz 33 — Remote
// Command Execution). Komut ANINDA çalışmaz — `pending` olarak
// oluşturulur, Agent'ın command-poll döngüsü çekip çalıştırır ve
// gerçek sonucu bildirir (bkz. `pollAgentCommand`, kısa client-side
// polling ile terminal duruma kadar beklenir).
export type AgentCommandType =
  | "kill_process"
  | "service_control"
  | "refresh_inventory"
  | "power_control"
  | "uninstall_service"
  | "update_self"
  | "check_updates"
  | "install_update";
export type AgentCommandAction =
  | "kill"
  | "start"
  | "stop"
  | "restart"
  | "collect"
  | "reboot"
  | "shutdown"
  | "logoff"
  | "uninstall"
  | "update"
  | "scan"
  | "install";
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

// ============================================================
// Faz 46 — Auth/RBAC + PAM (Privileged Access Management).
// `apps/api/app/auth/models.py`/`app/pam/models.py` ile birebir.
// ============================================================

export type UserRole = "ADMIN" | "OPERATOR" | "VIEWER";
// Faz 65 — bilet-modülüne özel rol ekseni (mevcut `role`'dan bağımsız):
// TECHNICIAN/ADMIN tüm biletleri görür, REQUESTER yalnızca kendi açtığını.
export type TicketRole = "REQUESTER" | "TECHNICIAN" | "ADMIN";

export type CurrentUser = {
  id: string;
  username: string;
  role: UserRole;
  full_name: string | null;
  is_active: boolean;
  // Faz 49 — bu yerel hesabın bağlı olduğu AD kullanıcı adı (sAMAccountName),
  // bağlı değilse null.
  ad_username: string | null;
  permissions: Permission[];
  ticket_role: TicketRole;
  created_at: string;
  updated_at: string;
};

export type LoginResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in_seconds: number;
  user: CurrentUser;
};

export async function loginRequest(username: string, password: string): Promise<LoginResponse> {
  const response = await fetch(`${API_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    await throwApiError(response, "Giriş başarısız");
  }
  return response.json();
}

export async function fetchMe(token: string): Promise<CurrentUser> {
  const response = await fetch(`${API_URL}/api/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    await throwApiError(response, "Kullanıcı bilgisi alınamadı");
  }
  return response.json();
}

// Tüm `/api/pam/*` çağrıları bu yardımcıyı kullanır — token yoksa
// (login sayfası dışında bir yerden çağrılırsa) sessizce başarısız
// OLMAK yerine açık bir hata fırlatır.
function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

export type UserCreateRequest = {
  username: string;
  password: string;
  role: UserRole;
  full_name?: string | null;
  ticket_role?: TicketRole;
};

export type UserUpdateRequest = {
  role?: UserRole;
  full_name?: string | null;
  is_active?: boolean;
  password?: string | null;
  ad_username?: string | null;
  ticket_role?: TicketRole;
};

export async function fetchPamUsers(token: string): Promise<CurrentUser[]> {
  const response = await fetch(`${API_URL}/api/pam/users`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Kullanıcılar alınamadı");
  return response.json();
}

export async function fetchPamUser(token: string, userId: string): Promise<CurrentUser> {
  const response = await fetch(`${API_URL}/api/pam/users/${userId}`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Kullanıcı alınamadı");
  return response.json();
}

export async function createPamUser(token: string, payload: UserCreateRequest): Promise<CurrentUser> {
  const response = await fetch(`${API_URL}/api/pam/users`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "Kullanıcı oluşturulamadı");
  return response.json();
}

export type UserCreateFromAdRequest = {
  ad_username: string;
  role: UserRole;
};

// Faz 52 — "Active Directory'den İçe Aktar". Admin'in ELLE tetiklediği
// bir provizyon — `POST /api/pam/users` (yerel, parola gerektirir) ile
// AYNI endpoint'e BİLİNÇLİ olarak eklenmedi (gövde şekli yeterince
// farklı), bkz. app/routes/pam_users.py::create_user_from_ad_route.
export async function createPamUserFromAd(token: string, payload: UserCreateFromAdRequest): Promise<CurrentUser> {
  const response = await fetch(`${API_URL}/api/pam/users/from-ad`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "AD kullanıcısı içe aktarılamadı");
  return response.json();
}

export async function updatePamUser(token: string, userId: string, payload: UserUpdateRequest): Promise<CurrentUser> {
  const response = await fetch(`${API_URL}/api/pam/users/${userId}`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "Kullanıcı güncellenemedi");
  return response.json();
}

export async function updatePamUserPermissions(token: string, userId: string, permissions: Permission[]): Promise<CurrentUser> {
  const response = await fetch(`${API_URL}/api/pam/users/${userId}/permissions`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify({ permissions }),
  });
  if (!response.ok) await throwApiError(response, "İzinler güncellenemedi");
  return response.json();
}

export type VaultCredentialType = "password" | "ssh_key";

export type VaultCredential = {
  id: string;
  name: string;
  credential_type: VaultCredentialType;
  username: string;
  domain: string | null;
  secret_masked: string;
  created_at: string;
  updated_at: string;
};

export type VaultCredentialCreateRequest = {
  name: string;
  credential_type: VaultCredentialType;
  username: string;
  domain?: string | null;
  password?: string | null;
  private_key?: string | null;
  passphrase?: string | null;
};

export type VaultCredentialReveal = {
  id: string;
  credential_type: VaultCredentialType;
  password: string | null;
  private_key: string | null;
  passphrase: string | null;
};

export async function fetchVaultCredentials(token: string): Promise<VaultCredential[]> {
  const response = await fetch(`${API_URL}/api/pam/vault`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Kasa hesapları alınamadı");
  return response.json();
}

export async function createVaultCredential(token: string, payload: VaultCredentialCreateRequest): Promise<VaultCredential> {
  const response = await fetch(`${API_URL}/api/pam/vault`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "Kasa hesabı oluşturulamadı");
  return response.json();
}

export async function deleteVaultCredential(token: string, credentialId: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/pam/vault/${credentialId}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!response.ok && response.status !== 204) await throwApiError(response, "Kasa hesabı silinemedi");
}

export async function revealVaultCredential(token: string, credentialId: string): Promise<VaultCredentialReveal> {
  const response = await fetch(`${API_URL}/api/pam/vault/${credentialId}/reveal`, {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!response.ok) await throwApiError(response, "Kasa hesabı görüntülenemedi");
  return response.json();
}

export type PamAccessRule = {
  id: string;
  // Faz 49 — TAM OLARAK biri dolu: `user_id`+`username` (yerel kural)
  // VEYA `ad_group_id`+`ad_group_name` (AD grup kuralı).
  user_id: string | null;
  username: string | null;
  ad_group_id: string | null;
  ad_group_name: string | null;
  // Faz 55 — cihaz hedefi de TAM OLARAK biri dolu: `asset_id` (tek
  // cihaz), `tag_id` (etiket) VEYA `server_group_id` (statik grup).
  asset_id: string | null;
  asset_hostname: string | null;
  asset_ip_address: string | null;
  tag_id: string | null;
  tag_name: string | null;
  server_group_id: string | null;
  server_group_name: string | null;
  credential_id: string;
  credential_name: string;
  allow_rdp: boolean;
  allow_ssh: boolean;
  // Faz 76 — PAM Web Konsolu (zero-knowledge HTTPS kimlik enjeksiyonu).
  allow_web: boolean;
  // Faz 54 — kural SİLİNMEDEN geçici olarak devre dışı bırakılabilir.
  is_active: boolean;
  max_session_duration_mins: number;
  valid_until: string | null;
  created_at: string;
  updated_at: string;
};

export type PamAccessRuleCreateRequest = {
  // Faz 49 — TAM OLARAK biri gönderilmeli (backend `model_validator`
  // ile doğrular, ikisi de/hiçbiri gönderilirse 422 döner).
  user_id?: string;
  ad_group_id?: string;
  // Faz 55 — cihaz hedefi de TAM OLARAK biri gönderilmeli.
  asset_id?: string;
  tag_id?: string;
  server_group_id?: string;
  credential_id: string;
  allow_rdp?: boolean;
  allow_ssh?: boolean;
  allow_web?: boolean;
  max_session_duration_mins?: number;
  valid_until?: string | null;
};

export type PamAccessRuleUpdateRequest = {
  credential_id?: string;
  allow_rdp?: boolean;
  allow_ssh?: boolean;
  allow_web?: boolean;
  is_active?: boolean;
  max_session_duration_mins?: number;
  valid_until?: string | null;
};

export type PamRulesQuery = {
  search?: string;
  limit?: number;
  offset?: number;
};

export async function fetchPamRules(token: string, query: PamRulesQuery = {}): Promise<PamAccessRule[]> {
  const params = new URLSearchParams();
  if (query.search) params.set("search", query.search);
  if (query.limit != null) params.set("limit", String(query.limit));
  if (query.offset != null) params.set("offset", String(query.offset));
  const qs = params.toString();
  const response = await fetch(`${API_URL}/api/pam/rules${qs ? `?${qs}` : ""}`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Erişim kuralları alınamadı");
  return response.json();
}

export async function createPamRule(token: string, payload: PamAccessRuleCreateRequest): Promise<PamAccessRule> {
  const response = await fetch(`${API_URL}/api/pam/rules`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "Erişim kuralı oluşturulamadı");
  return response.json();
}

export async function updatePamRule(token: string, ruleId: string, payload: PamAccessRuleUpdateRequest): Promise<PamAccessRule> {
  const response = await fetch(`${API_URL}/api/pam/rules/${ruleId}`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "Erişim kuralı güncellenemedi");
  return response.json();
}

export async function deletePamRule(token: string, ruleId: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/pam/rules/${ruleId}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!response.ok && response.status !== 204) await throwApiError(response, "Erişim kuralı silinemedi");
}

// ============================================================
// Faz 55 — PAM Cihaz Etiketleri (Tags) + Statik Cihaz Grupları (Server
// Groups). `apps/api/app/pam/models.py` ile birebir.
// ============================================================

export type PamTag = {
  id: string;
  name: string;
  created_at: string;
};

export type PamTagAsset = {
  id: string;
  hostname: string | null;
  ip_address: string | null;
};

export async function fetchPamTags(token: string): Promise<PamTag[]> {
  const response = await fetch(`${API_URL}/api/pam/tags`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Etiketler alınamadı");
  return response.json();
}

export async function createPamTag(token: string, name: string): Promise<PamTag> {
  const response = await fetch(`${API_URL}/api/pam/tags`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ name }),
  });
  if (!response.ok) await throwApiError(response, "Etiket oluşturulamadı");
  return response.json();
}

export async function deletePamTag(token: string, tagId: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/pam/tags/${tagId}`, { method: "DELETE", headers: authHeaders(token) });
  if (!response.ok && response.status !== 204) await throwApiError(response, "Etiket silinemedi");
}

export async function fetchPamTagAssets(token: string, tagId: string): Promise<PamTagAsset[]> {
  const response = await fetch(`${API_URL}/api/pam/tags/${tagId}/assets`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Etiketli cihazlar alınamadı");
  return response.json();
}

export async function assignPamTag(token: string, tagId: string, assetId: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/pam/tags/${tagId}/assets/${assetId}`, {
    method: "PUT",
    headers: authHeaders(token),
  });
  if (!response.ok && response.status !== 204) await throwApiError(response, "Etiket atanamadı");
}

export async function unassignPamTag(token: string, tagId: string, assetId: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/pam/tags/${tagId}/assets/${assetId}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!response.ok && response.status !== 204) await throwApiError(response, "Etiket kaldırılamadı");
}

export type ServerGroup = {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type ServerGroupAsset = {
  id: string;
  hostname: string | null;
  ip_address: string | null;
};

export async function fetchServerGroups(token: string): Promise<ServerGroup[]> {
  const response = await fetch(`${API_URL}/api/pam/server-groups`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Cihaz grupları alınamadı");
  return response.json();
}

export async function createServerGroup(token: string, name: string, description?: string | null): Promise<ServerGroup> {
  const response = await fetch(`${API_URL}/api/pam/server-groups`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ name, description: description || null }),
  });
  if (!response.ok) await throwApiError(response, "Cihaz grubu oluşturulamadı");
  return response.json();
}

export async function updateServerGroup(
  token: string,
  groupId: string,
  payload: { name?: string; description?: string | null },
): Promise<ServerGroup> {
  const response = await fetch(`${API_URL}/api/pam/server-groups/${groupId}`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "Cihaz grubu güncellenemedi");
  return response.json();
}

export async function deleteServerGroup(token: string, groupId: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/pam/server-groups/${groupId}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!response.ok && response.status !== 204) await throwApiError(response, "Cihaz grubu silinemedi");
}

export async function fetchServerGroupAssets(token: string, groupId: string): Promise<ServerGroupAsset[]> {
  const response = await fetch(`${API_URL}/api/pam/server-groups/${groupId}/assets`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Grup üyeleri alınamadı");
  return response.json();
}

export async function addServerGroupMember(token: string, groupId: string, assetId: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/pam/server-groups/${groupId}/assets/${assetId}`, {
    method: "PUT",
    headers: authHeaders(token),
  });
  if (!response.ok && response.status !== 204) await throwApiError(response, "Cihaz gruba eklenemedi");
}

export async function removeServerGroupMember(token: string, groupId: string, assetId: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/pam/server-groups/${groupId}/assets/${assetId}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!response.ok && response.status !== 204) await throwApiError(response, "Cihaz gruptan kaldırılamadı");
}

// ============================================================
// Faz 56 — PAM Erişim Talepleri (Access Requests). `apps/api/app/pam/
// models.py`'deki `AccessRequest*` ile birebir. Onaylama YENİ bir
// yetkilendirme mekanizması AÇMAZ — mevcut `pam_access_rules`'u
// genişletir/oluşturur (bkz. backend `service.py::
// approve_access_request`).
// ============================================================

export type AccessRequestStatus = "pending" | "approved" | "rejected";

export type PamAccessRequest = {
  id: string;
  requester_id: string;
  requester_username: string;
  // Faz 55'in cihaz-hedefi XOR'uyla AYNI desen — TAM OLARAK biri dolu.
  asset_id: string | null;
  asset_hostname: string | null;
  asset_ip_address: string | null;
  tag_id: string | null;
  tag_name: string | null;
  server_group_id: string | null;
  server_group_name: string | null;
  protocol: "ssh" | "rdp";
  business_reason: string;
  requested_duration_mins: number;
  status: AccessRequestStatus;
  reviewed_by: string | null;
  reviewed_by_username: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string;
};

export type AccessRequestCreateRequest = {
  asset_id?: string;
  tag_id?: string;
  server_group_id?: string;
  protocol: "ssh" | "rdp";
  business_reason: string;
  requested_duration_mins?: number;
};

export async function createAccessRequest(token: string, payload: AccessRequestCreateRequest): Promise<PamAccessRequest> {
  const response = await fetch(`${API_URL}/api/pam/access-requests`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "Erişim talebi oluşturulamadı");
  return response.json();
}

export async function fetchMyAccessRequests(token: string): Promise<PamAccessRequest[]> {
  const response = await fetch(`${API_URL}/api/pam/access-requests/mine`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Erişim taleplerim alınamadı");
  return response.json();
}

export async function fetchAccessRequests(token: string, status?: AccessRequestStatus): Promise<PamAccessRequest[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const qs = params.toString();
  const response = await fetch(`${API_URL}/api/pam/access-requests${qs ? `?${qs}` : ""}`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Erişim talepleri alınamadı");
  return response.json();
}

export async function approveAccessRequest(
  token: string,
  requestId: string,
  credentialId: string,
  reviewNote?: string,
): Promise<PamAccessRequest> {
  const response = await fetch(`${API_URL}/api/pam/access-requests/${requestId}/approve`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ credential_id: credentialId, review_note: reviewNote || null }),
  });
  if (!response.ok) await throwApiError(response, "Erişim talebi onaylanamadı");
  return response.json();
}

export async function rejectAccessRequest(token: string, requestId: string, reviewNote?: string): Promise<PamAccessRequest> {
  const response = await fetch(`${API_URL}/api/pam/access-requests/${requestId}/reject`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ review_note: reviewNote || null }),
  });
  if (!response.ok) await throwApiError(response, "Erişim talebi reddedilemedi");
  return response.json();
}

export type AuthorizedAsset = {
  asset_id: string;
  asset_hostname: string | null;
  asset_ip_address: string | null;
  allow_rdp: boolean;
  allow_ssh: boolean;
  allow_web: boolean;
  max_session_duration_mins: number;
  valid_until: string | null;
  // Faz 58 — "PAM Launchpad" yükseltmesi: `assets.status` (gerçek
  // discovery/SNMP verisi) + Faz 51'in session_registry çapraz
  // kontrollü aktif oturum sayısından türetilir, ikisi de uydurulmaz.
  is_online: boolean;
  active_sessions_count: number;
};

export async function fetchMyAccess(token: string): Promise<AuthorizedAsset[]> {
  const response = await fetch(`${API_URL}/api/pam/my-access`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Yetkili sunucular alınamadı");
  return response.json();
}

export type PamSessionLog = {
  id: string;
  user_id: string;
  username: string;
  asset_id: string;
  asset_hostname: string | null;
  asset_ip_address: string | null;
  credential_id: string | null;
  credential_name: string | null;
  protocol: "ssh" | "rdp";
  started_at: string;
  ended_at: string | null;
  // 'user_closed' | 'timeout' | 'error' | 'terminated_by_admin' (Faz 50)
  end_reason: string | null;
  client_ip: string | null;
  // Faz 50 — yalnızca RDP: guacd `.guac` kayıt dosyası varsa dolu.
  recording_file_path: string | null;
  terminated_by: string | null;
};

export type PamAuditQuery = {
  search?: string;
  protocol?: "rdp" | "ssh";
  reason?: string;
  limit?: number;
  offset?: number;
};

export async function fetchPamAudit(token: string, activeOnly: boolean, query: PamAuditQuery = {}): Promise<PamSessionLog[]> {
  const params = new URLSearchParams();
  params.set("active", String(activeOnly));
  if (query.search) params.set("search", query.search);
  if (query.protocol) params.set("protocol", query.protocol);
  if (query.reason) params.set("reason", query.reason);
  if (query.limit != null) params.set("limit", String(query.limit));
  if (query.offset != null) params.set("offset", String(query.offset));
  const response = await fetch(`${API_URL}/api/pam/audit?${params.toString()}`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Denetim kaydı alınamadı");
  return response.json();
}

// ============================================================
// Faz 50 — Canlı Oturum Sonlandırma, Tuş Loglama, Oturum Kaydı Replay.
// `apps/api/app/routes/pam_audit.py` ile birebir.
// ============================================================

export async function terminatePamSession(token: string, sessionId: string): Promise<PamSessionLog> {
  const response = await fetch(`${API_URL}/api/pam/audit/${sessionId}/terminate`, {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!response.ok) await throwApiError(response, "Oturum sonlandırılamadı");
  return response.json();
}

export type PamKeystroke = {
  id: string;
  recorded_at: string;
  data: string;
};

export async function fetchSessionKeystrokes(token: string, sessionId: string): Promise<PamKeystroke[]> {
  const response = await fetch(`${API_URL}/api/pam/audit/${sessionId}/keystrokes`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Tuş logu alınamadı");
  return response.json();
}

// Oturum kaydı (`.guac` dosyası) — `<video>` etiketiyle DEĞİL,
// `guacamole-common-js`'in `Guacamole.SessionRecording`'i ile
// TARAYICIDA replay edilir (bkz. `components/SessionReplayModal.tsx`)
// — bu yüzden bir URL değil, doğrudan bir `Blob` döner (JWT header'ı
// gerektiği için çıplak bir `<video src>` zaten kullanılamazdı).
export async function fetchSessionRecordingBlob(token: string, sessionId: string): Promise<Blob> {
  const response = await fetch(`${API_URL}/api/pam/audit/${sessionId}/recording`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Oturum kaydı alınamadı");
  return response.blob();
}

// Faz 53 — kayıttaki GERÇEK tuş basma olaylarından türetilen zaman
// çubuğu işaretleri (ms ofset listesi) — bkz. `app/pam/
// recording_analysis.py`. Kayıt yoksa (SSH oturumu vb.) boş liste.
export async function fetchSessionActivityMarkers(token: string, sessionId: string): Promise<number[]> {
  const response = await fetch(`${API_URL}/api/pam/audit/${sessionId}/activity-markers`, {
    headers: authHeaders(token),
  });
  if (!response.ok) await throwApiError(response, "Zaman çubuğu işaretleri alınamadı");
  return response.json();
}

// Faz 75 — İnaktif Süre Atlama. Kayıttaki GERÇEK `sync` zaman
// damgalarından çıkarılan, aralarında hiçbir aktivite olmayan boşluklar.
export type IdleGap = { start_ms: number; end_ms: number };

export async function fetchSessionIdleGaps(token: string, sessionId: string): Promise<IdleGap[]> {
  const response = await fetch(`${API_URL}/api/pam/audit/${sessionId}/idle-gaps`, {
    headers: authHeaders(token),
  });
  if (!response.ok) await throwApiError(response, "İnaktif süre bilgisi alınamadı");
  return response.json();
}

// ============================================================
// Faz 49 — LDAP / Active Directory Bağlantı Yönetimi.
// `apps/api/app/services/ldap_models.py` ile birebir.
// ============================================================

export type LdapConfig = {
  host: string;
  port: number;
  use_ssl: boolean;
  domain_fqdn: string;
  base_dn: string;
  bind_dn: string;
  bind_password_masked: string;
  last_sync_status: string | null;
  last_sync_error: string | null;
  last_sync_at: string | null;
  updated_at: string;
};

export type LdapConfigRequest = {
  host: string;
  port?: number;
  use_ssl?: boolean;
  domain_fqdn: string;
  base_dn: string;
  bind_dn: string;
  // `null`/alan hiç gönderilmemesi "mevcut kayıtlı parolayı koru"
  // anlamına gelir (bkz. app/routes/ldap_settings.py::
  // _resolve_bind_password) — Vault kimlik bilgisi güncellemesiyle AYNI
  // ilke.
  bind_password: string | null;
};

export type LdapTestResult = {
  success: boolean;
  message: string;
};

export type LdapSyncResult = {
  groups_synced: number;
  users_synced: number;
  memberships_synced: number;
};

export type AdGroup = {
  id: string;
  distinguished_name: string;
  name: string;
  synced_at: string;
};

export type AdUser = {
  id: string;
  distinguished_name: string;
  username: string;
  display_name: string | null;
  email: string | null;
  synced_at: string;
};

export async function fetchLdapConfig(token: string): Promise<LdapConfig | null> {
  const response = await fetch(`${API_URL}/api/settings/ldap`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "LDAP yapılandırması alınamadı");
  return response.json();
}

export async function updateLdapConfig(token: string, payload: LdapConfigRequest): Promise<LdapConfig> {
  const response = await fetch(`${API_URL}/api/settings/ldap`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "LDAP yapılandırması kaydedilemedi");
  return response.json();
}

export async function testLdapConnection(token: string, payload: LdapConfigRequest): Promise<LdapTestResult> {
  const response = await fetch(`${API_URL}/api/settings/ldap/test`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "Bağlantı testi başarısız");
  return response.json();
}

export async function syncLdapDirectory(token: string): Promise<LdapSyncResult> {
  const response = await fetch(`${API_URL}/api/settings/ldap/sync`, {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!response.ok) await throwApiError(response, "Senkronizasyon başarısız");
  return response.json();
}

export async function fetchAdGroups(token: string): Promise<AdGroup[]> {
  const response = await fetch(`${API_URL}/api/settings/ldap/groups`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "AD grupları alınamadı");
  return response.json();
}

export async function fetchAdUsers(token: string): Promise<AdUser[]> {
  const response = await fetch(`${API_URL}/api/settings/ldap/users`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "AD kullanıcıları alınamadı");
  return response.json();
}

// ============================================================
// Faz 66 — SMTP Yapılandırması (Ayarlar > SMTP).
// `apps/api/app/routes/smtp_settings.py` ile birebir.
// ============================================================

export type SmtpEncryption = "tls" | "ssl" | "none";

export type SmtpConfig = {
  enabled: boolean;
  server: string;
  port: number;
  encryption: SmtpEncryption;
  username: string;
  password_set: boolean;
  from_email: string;
  from_name: string;
  it_group_email: string;
  base_url: string;
  last_test_status: string | null;
  last_test_error: string | null;
  last_test_at: string | null;
  updated_at: string;
};

export type SmtpConfigRequest = {
  enabled: boolean;
  server: string;
  port: number;
  encryption: SmtpEncryption;
  username: string;
  // `null` → "mevcut kayıtlı parolayı koru" (LDAP bind parolası deseniyle aynı).
  password: string | null;
  from_email: string;
  from_name: string;
  it_group_email: string;
  base_url: string;
};

export type SmtpTestResult = { success: boolean; message: string };

export async function fetchSmtpConfig(token: string): Promise<SmtpConfig | null> {
  const response = await fetch(`${API_URL}/api/settings/smtp`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "SMTP yapılandırması alınamadı");
  return response.json();
}

export async function updateSmtpConfig(token: string, payload: SmtpConfigRequest): Promise<SmtpConfig> {
  const response = await fetch(`${API_URL}/api/settings/smtp`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "SMTP yapılandırması kaydedilemedi");
  return response.json();
}

export async function testSmtpConnection(token: string, to: string): Promise<SmtpTestResult> {
  const response = await fetch(`${API_URL}/api/settings/smtp/test`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ to }),
  });
  if (!response.ok) await throwApiError(response, "SMTP testi başarısız");
  return response.json();
}

// ============================================================
// Faz 72 — vCenter/vSphere.
// ============================================================

export type VCenterConfig = {
  host: string;
  port: number;
  username: string;
  verify_ssl: boolean;
  last_test_status: string | null;
  last_test_error: string | null;
  last_test_at: string | null;
  updated_at: string;
};

export type VCenterConfigRequest = {
  host: string;
  port: number;
  username: string;
  // `null` → "mevcut kayıtlı parolayı koru" (LDAP/SMTP ile aynı desen).
  password: string | null;
  verify_ssl: boolean;
};

export type VCenterTestResult = { success: boolean; message: string };

export type VCenterPowerState = "POWERED_ON" | "POWERED_OFF" | "SUSPENDED" | "UNKNOWN";
export type VCenterPowerAction = "start" | "stop" | "reset" | "guest_reboot";

export type VCenterVmSummary = {
  id: string;
  name: string;
  power_state: VCenterPowerState;
  // Kaynak TAHSİSİ — anlık kullanım yüzdesi DEĞİL (bkz. VCenterVmDetail).
  cpu_count: number | null;
  memory_mb: number | null;
  ip_address: string | null;
  guest_os: string | null;
};

export type VCenterVmDetail = VCenterVmSummary & {
  guest_hostname: string | null;
  // Faz 72 dürüstlük sınırı: vCenter REST Inventory API'sinde anlık
  // CPU/RAM kullanım yüzdesi yok (Performance Manager/SOAP gerekir) —
  // bu alanlar HER ZAMAN null, uydurulmaz.
  cpu_usage_percent: number | null;
  memory_usage_percent: number | null;
};

export type VCenterHostSummary = {
  id: string;
  name: string;
  connection_state: string;
  power_state: string;
};

export type VCenterDatastoreSummary = {
  id: string;
  name: string;
  type: string;
  capacity_gb: number;
  free_gb: number;
};

export type VCenterSummary = {
  total_hosts: number;
  total_vms: number;
  powered_on_vms: number;
  total_vcpu_allocated: number;
  total_memory_gb_allocated: number;
  datastores: VCenterDatastoreSummary[];
};

export async function fetchVCenterConfig(token: string): Promise<VCenterConfig | null> {
  const response = await fetch(`${API_URL}/api/settings/vcenter`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "vCenter yapılandırması alınamadı");
  return response.json();
}

export async function updateVCenterConfig(token: string, payload: VCenterConfigRequest): Promise<VCenterConfig> {
  const response = await fetch(`${API_URL}/api/settings/vcenter`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "vCenter yapılandırması kaydedilemedi");
  return response.json();
}

export async function testVCenterConnection(token: string, payload: VCenterConfigRequest): Promise<VCenterTestResult> {
  const response = await fetch(`${API_URL}/api/settings/vcenter/test`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "vCenter testi başarısız");
  return response.json();
}

export async function fetchVCenterSummary(token: string): Promise<VCenterSummary> {
  const response = await fetch(`${API_URL}/api/vcenter/summary`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "vCenter özeti alınamadı");
  return response.json();
}

export async function fetchVCenterVms(token: string): Promise<VCenterVmSummary[]> {
  const response = await fetch(`${API_URL}/api/vcenter/vms`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "VM listesi alınamadı");
  return response.json();
}

export async function fetchVCenterVmDetail(token: string, vmId: string): Promise<VCenterVmDetail> {
  const response = await fetch(`${API_URL}/api/vcenter/vms/${encodeURIComponent(vmId)}`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "VM detayı alınamadı");
  return response.json();
}

export async function fetchVCenterHosts(token: string): Promise<VCenterHostSummary[]> {
  const response = await fetch(`${API_URL}/api/vcenter/hosts`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Host listesi alınamadı");
  return response.json();
}

export async function performVCenterVmPowerAction(token: string, vmId: string, action: VCenterPowerAction): Promise<void> {
  const response = await fetch(`${API_URL}/api/vcenter/vms/${encodeURIComponent(vmId)}/power`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ action }),
  });
  if (!response.ok) await throwApiError(response, "Güç işlemi başarısız");
}

// Zero-Knowledge PAM SSH — `WS /api/pam/ssh/{assetId}?token=...`. JWT
// query string'de taşınıyor (tarayıcı native `WebSocket` API'si özel
// header GÖNDEREMEZ) — bkz. `apps/api/app/routes/pam_ssh.py` docstring'i.
export function pamSshWebSocketUrl(assetId: string, token: string): string {
  const origin = backendOrigin().replace(/^http/, "ws");
  return `${origin}/api/pam/ssh/${assetId}?token=${encodeURIComponent(token)}`;
}

// Faz 48 — Gerçek Zero-Knowledge PAM RDP: `WS /api/pam/rdp/{assetId}
// ?token=...&width=...&height=...&dpi=...`. `.rdp` dosya indirme akışı
// (Faz 47) TAMAMEN KALDIRILDI — kullanıcının açık isteğiyle, artık
// `guacamole-common-js` ile tarayıcıda render edilen canlı bir HTML5
// oturumu (bkz. `components/GuacamoleRdpViewer.tsx`, backend `app/
// routes/pam_rdp.py`/`app/pam/guacd.py`). JWT query string'de —
// `pamSshWebSocketUrl` ile AYNI, tarayıcı WebSocket API kısıtlaması
// yüzünden belgelenmiş ödünleşim.
// GERÇEK tarayıcıda bulunan bir hata (bkz. `components/
// GuacamoleRdpViewer.tsx`): `guacamole-common-js`'in `Guacamole.
// WebSocketTunnel`'ı `Guacamole.Client.connect(data)` çağrıldığında
// HER ZAMAN `new WebSocket(tunnelURL + "?" + data, ...)` yapıyor —
// `tunnelURL`'in KENDİSİNE query string koymak (`?token=...`) bu
// yüzden İKİNCİ bir `?` ekleyip URL'yi bozuyor (backend'in `dpi` query
// param'ı `"96?"` gibi geçersiz bir değer alıp isteği reddediyordu).
// Doğru kullanım: `pamRdpWebSocketUrl` yalnızca ÇIPLAK tünel adresini
// döner, gerçek query string'i `pamRdpConnectData` üretir ve
// `client.connect(data)`'ye O geçirilir.
export function pamRdpWebSocketUrl(assetId: string): string {
  const origin = backendOrigin().replace(/^http/, "ws");
  return `${origin}/api/pam/rdp/${assetId}`;
}

export function pamRdpConnectData(token: string, width: number, height: number, dpi: number): string {
  return new URLSearchParams({
    token,
    width: String(Math.round(width)),
    height: String(Math.round(height)),
    dpi: String(Math.round(dpi)),
  }).toString();
}

// ============================================================
// Faz 76 — PAM Web Konsolu (zero-knowledge HTTPS kimlik enjeksiyonu).
// ============================================================

export type WebConsoleProfile = {
  asset_id: string;
  port: number;
  verify_ssl: boolean;
  login_path: string;
  username_field: string;
  password_field: string;
  updated_at: string;
};

export type WebConsoleProfileRequest = {
  port: number;
  verify_ssl: boolean;
  login_path: string;
  username_field: string;
  password_field: string;
};

export type WebConsoleSession = {
  session_id: string;
  proxy_url: string;
  max_session_duration_mins: number;
};

export async function fetchWebConsoleProfile(token: string, assetId: string): Promise<WebConsoleProfile | null> {
  const response = await fetch(`${API_URL}/api/pam/web/profiles/${assetId}`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Web konsolu profili alınamadı");
  return response.json();
}

export async function saveWebConsoleProfile(
  token: string,
  assetId: string,
  payload: WebConsoleProfileRequest,
): Promise<WebConsoleProfile> {
  const response = await fetch(`${API_URL}/api/pam/web/profiles/${assetId}`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "Web konsolu profili kaydedilemedi");
  return response.json();
}

export async function deleteWebConsoleProfile(token: string, assetId: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/pam/web/profiles/${assetId}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!response.ok && response.status !== 204) await throwApiError(response, "Web konsolu profili silinemedi");
}

export async function startWebConsoleSession(token: string, assetId: string): Promise<WebConsoleSession> {
  const response = await fetch(`${API_URL}/api/pam/web/${assetId}/session`, {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!response.ok) await throwApiError(response, "Web konsolu oturumu başlatılamadı");
  return response.json();
}

export async function closeWebConsoleSession(token: string, sessionId: string): Promise<void> {
  await fetch(`${API_URL}/api/pam/web/${sessionId}/close`, { method: "POST", headers: authHeaders(token) }).catch(() => {
    /* sayfadan ayrılırken best-effort — başarısız olsa da TTL kendi kendine sona erer */
  });
}

// Faz 51 — Canlı Oturum İzleme (Shadowing): `WS /api/pam/audit/{id}/
// shadow?token=...`. `pamRdpWebSocketUrl`'in AKSİNE burada width/height/
// dpi YOK — bu bağlantı guacd ile KENDİ el sıkışmasını yapmıyor, mevcut
// birincil bağlantının çıktısını salt-okunur olarak yayınlıyor (bkz.
// `app/routes/pam_audit.py::shadow_session_route`). `pamRdpConnectData`
// ile AYNI "tunnel URL çıplak, query string connect(data)'ye" kuralı
// burada da geçerli.
export function pamShadowWebSocketUrl(sessionId: string): string {
  const origin = backendOrigin().replace(/^http/, "ws");
  return `${origin}/api/pam/audit/${sessionId}/shadow`;
}

export function pamShadowConnectData(token: string): string {
  return new URLSearchParams({ token }).toString();
}

// ============================================================
// Faz 62 — IT Helpdesk / Arıza Yönetimi (Ticket Management).
// `apps/api/app/tickets/models.py` ile birebir. PAM'den bağımsız;
// tüm çağrılar `TICKETS_VIEW` iznine tabidir (backend `require_
// permission`, frontend `RequirePermission`). `/api/v1` YOK.
// ============================================================

export type TicketPriority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type TicketStatus = "OPEN" | "IN_PROGRESS" | "WAITING_USER" | "RESOLVED" | "CLOSED";
export type TicketCommentEvent = "created" | "comment" | "status_change" | "assignment";

export type TicketComment = {
  id: string;
  ticket_id: string;
  author_id: string;
  author_username: string;
  event: TicketCommentEvent;
  body: string | null;
  status_from: TicketStatus | null;
  status_to: TicketStatus | null;
  assigned_from_username: string | null;
  assigned_to_username: string | null;
  created_at: string;
};

export type Ticket = {
  id: string;
  ticket_number: string;
  title: string;
  description: string;
  // Faz 63 — dinamik taksonomi (id + gösterim adı).
  category_id: string | null;
  category_name: string | null;
  department_id: string | null;
  department_name: string | null;
  priority: TicketPriority;
  status: TicketStatus;
  created_by: string;
  created_by_username: string;
  assigned_to: string | null;
  assigned_to_username: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  sla_due_at: string | null;
  comments: TicketComment[];
};

// Faz 63 — departman/kategori (aynı şekil).
export type TicketTaxonomyItem = { id: string; name: string; is_active: boolean };

export type TicketStats = {
  open_tickets: number;
  assigned_to_me: number;
  critical_or_overdue: number;
  resolved_this_month: number;
};

export type TicketListResponse = {
  tickets: Ticket[];
  total: number;
  stats: TicketStats;
};

export type TicketCreateRequest = {
  title: string;
  description?: string;
  category_id: string;
  department_id?: string | null;
  priority?: TicketPriority;
};

export type TicketQuery = {
  status?: TicketStatus;
  priority?: TicketPriority;
  category_id?: string;
  department_id?: string;
  search?: string;
  overdue?: boolean;
  mine?: boolean;
  limit?: number;
  offset?: number;
};

function ticketQueryParams(query: TicketQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.status) params.set("status", query.status);
  if (query.priority) params.set("priority", query.priority);
  if (query.category_id) params.set("category_id", query.category_id);
  if (query.department_id) params.set("department_id", query.department_id);
  if (query.search) params.set("search", query.search);
  if (query.overdue) params.set("overdue", "true");
  if (query.mine) params.set("mine", "true");
  if (query.limit != null) params.set("limit", String(query.limit));
  if (query.offset != null) params.set("offset", String(query.offset));
  return params;
}

export async function fetchTickets(token: string, query: TicketQuery = {}): Promise<TicketListResponse> {
  const qs = ticketQueryParams(query).toString();
  const response = await fetch(`${API_URL}/api/tickets${qs ? `?${qs}` : ""}`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Biletler alınamadı");
  return response.json();
}

// Faz 69 — CSV dışa aktarma. Auth header'lı `fetch` + Blob indirmesi
// (endpoint `TICKETS_VIEW` gerektirir; native `<a href>` header
// gönderemez, bu yüzden içeriği çekip programatik indiriyoruz).
export async function downloadTicketsCsv(token: string, query: TicketQuery = {}): Promise<void> {
  const params = ticketQueryParams(query);
  params.delete("limit");
  params.delete("offset");
  const qs = params.toString();
  const response = await fetch(`${API_URL}/api/tickets/export.csv${qs ? `?${qs}` : ""}`, {
    headers: authHeaders(token),
  });
  if (!response.ok) await throwApiError(response, "CSV dışa aktarılamadı");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "tickets.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ---- Faz 63 — Departman + Kategori (taksonomi) yönetimi -------------

async function fetchTicketTaxonomy(
  token: string,
  kind: "departments" | "categories",
  includeInactive = false,
): Promise<TicketTaxonomyItem[]> {
  const qs = includeInactive ? "?include_inactive=true" : "";
  const response = await fetch(`${API_URL}/api/tickets/${kind}${qs}`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Liste alınamadı");
  return response.json();
}

async function createTicketTaxonomy(
  token: string,
  kind: "departments" | "categories",
  name: string,
): Promise<TicketTaxonomyItem> {
  const response = await fetch(`${API_URL}/api/tickets/${kind}`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ name }),
  });
  if (!response.ok) await throwApiError(response, "Eklenemedi");
  return response.json();
}

async function deleteTicketTaxonomy(token: string, kind: "departments" | "categories", id: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/tickets/${kind}/${id}`, { method: "DELETE", headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Silinemedi");
}

export const fetchTicketDepartments = (token: string, includeInactive = false) =>
  fetchTicketTaxonomy(token, "departments", includeInactive);
export const fetchTicketCategories = (token: string, includeInactive = false) =>
  fetchTicketTaxonomy(token, "categories", includeInactive);
export const createTicketDepartment = (token: string, name: string) => createTicketTaxonomy(token, "departments", name);
export const createTicketCategory = (token: string, name: string) => createTicketTaxonomy(token, "categories", name);
export const deleteTicketDepartment = (token: string, id: string) => deleteTicketTaxonomy(token, "departments", id);
export const deleteTicketCategory = (token: string, id: string) => deleteTicketTaxonomy(token, "categories", id);

// ---- Faz 67 — SLA politikası --------------------------------------
// `{ LOW: 168, MEDIUM: 72, HIGH: 24, CRITICAL: 4 }` (öncelik → saat).
export type SlaPolicy = Record<TicketPriority, number>;

export async function fetchSlaPolicy(token: string): Promise<SlaPolicy> {
  const response = await fetch(`${API_URL}/api/tickets/sla-policy`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "SLA politikası alınamadı");
  return response.json();
}

export async function updateSlaPolicy(token: string, priority: TicketPriority, slaHours: number): Promise<SlaPolicy> {
  const response = await fetch(`${API_URL}/api/tickets/sla-policy/${priority}`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify({ sla_hours: slaHours }),
  });
  if (!response.ok) await throwApiError(response, "SLA politikası kaydedilemedi");
  return response.json();
}

// ---- Faz 68 — salt-okunur bilet metrikleri -----------------------
export type TicketMetrics = {
  total: number;
  open_tickets: number;
  closed_tickets: number;
  overdue_open: number;
  avg_resolution_hours: number | null;
  sla_compliance_pct: number | null;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  by_category: Record<string, number>;
  by_department: Record<string, number>;
  daily: { day: string; created: number; resolved: number }[];
};

export async function fetchTicketMetrics(token: string): Promise<TicketMetrics> {
  const response = await fetch(`${API_URL}/api/tickets/metrics`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Bilet metrikleri alınamadı");
  return response.json();
}

export async function fetchTicket(token: string, ticketId: string): Promise<Ticket> {
  const response = await fetch(`${API_URL}/api/tickets/${ticketId}`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Bilet detayı alınamadı");
  return response.json();
}

export async function createTicket(token: string, payload: TicketCreateRequest): Promise<Ticket> {
  const response = await fetch(`${API_URL}/api/tickets`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "Bilet oluşturulamadı");
  return response.json();
}

// Tek çağrıyla: opsiyonel yorum + opsiyonel durum + opsiyonel atama.
// `assignedTo === undefined` → atama değişmez; `null` → atama kaldırılır.
export async function addTicketComment(
  token: string,
  ticketId: string,
  payload: {
    body?: string;
    status?: TicketStatus;
    assigned_to?: string | null;
  },
): Promise<Ticket> {
  const response = await fetch(`${API_URL}/api/tickets/${ticketId}/comments`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await throwApiError(response, "Yorum eklenemedi");
  return response.json();
}

export type TicketAssignableUser = { id: string; username: string };

export async function fetchTicketAssignableUsers(token: string): Promise<TicketAssignableUser[]> {
  const response = await fetch(`${API_URL}/api/tickets/assignable-users`, { headers: authHeaders(token) });
  if (!response.ok) await throwApiError(response, "Kullanıcı listesi alınamadı");
  return response.json();
}
