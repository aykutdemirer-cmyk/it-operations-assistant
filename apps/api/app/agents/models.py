"""Agent alt sisteminin Pydantic modelleri (Faz 28) — hem API request/
response sözleşmesi hem de servis-katmanı domain tipleri olarak
kullanılır (bkz. `app/snmp/models.py`'nin aynı ikili rolü).

Lifecycle: Register -> Authentication (Bearer token) -> Heartbeat ->
Inventory -> Telemetry -> Monitoring (bkz. Faz 32+)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

AgentOS = Literal["windows", "linux"]

# Client'tan (agent süreci) gelen serbest metin alanlarına makul bir üst
# sınır — güvenilmeyen girdiye "limitsiz string" kabul etmeme ilkesi
# (Faz 30, kullanıcı talimatı §29). Gerçek hostname/interface/process/
# service isimleri bu sınırı asla aşmaz; aşan bir değer zaten bozuk/
# kötü niyetli bir payload'a işaret eder.
_MAX_NAME_LENGTH = 255

# `agents.last_heartbeat_at`'ten TÜRETİLİR — asla DB'de ayrı bir
# "status" sütunu olarak SAKLANMAZ (saklanan bir durum gerçekle
# çakışabilir/eskiyebilir; bu proje "gerçek veri, uydurma yok" ilkesini
# burada da uyguluyor). `online`: son heartbeat, eşik içinde
# (`AGENT_OFFLINE_THRESHOLD_SECONDS`, varsayılan 120s). `unknown`: hiç
# heartbeat gelmemiş (yeni kayıtlı). `offline`: eşik aşılmış.
AgentStatus = Literal["online", "offline", "unknown"]


class AgentRegistrationRequest(BaseModel):
    """`POST /api/agents/register` — agent kendi metadata'sını verir,
    sunucu yeni bir `agent_id` + tek seferlik bir bearer token üretir.

    `enrollment_code` (Faz 31) ZORUNLUDUR — geçerli, süresi dolmamış,
    daha önce kullanılmamış bir kod olmadan kayıt reddedilir (bkz.
    `app/agents/enrollment.py`, `docs/decisions.md`). Bu bir credential
    DEĞİLDİR, yalnızca "bu kaydı bir insan başlattı" onayıdır."""

    hostname: str = Field(max_length=_MAX_NAME_LENGTH)
    fqdn: str | None = Field(default=None, max_length=_MAX_NAME_LENGTH)
    os: AgentOS
    os_version: str | None = None
    architecture: str | None = None
    agent_version: str
    local_ip: str | None = None
    mac_address: str | None = None
    capabilities: list[str] = []
    enrollment_code: str = Field(max_length=32)


class EnrollmentCodeResponse(BaseModel):
    """`POST /api/agents/enrollment-codes` — kod bir credential
    DEĞİLDİR (tek başına hiçbir kaynağa erişim vermez), bu yüzden
    plaintext döndürülmesi güvenlik ilkesini ihlal etmez."""

    code: str
    expires_at: datetime


class EnrollmentCodeSummary(BaseModel):
    """`GET /api/agents/enrollment-codes` liste öğesi."""

    code: str
    created_at: datetime
    expires_at: datetime


class WindowsAgentDownloadInfo(BaseModel):
    """`GET /api/agents/download/windows/info` — gerçek build
    metadata'sı (`apps/agent/dist/build-info.json`, `packaging/windows/
    build.ps1` tarafından üretilir). `available=False` ise diğer
    alanlar `None` — hiçbir zaman uydurma bir versiyon/boyut
    gösterilmez (Faz 32)."""

    available: bool
    version: str | None = None
    filename: str | None = None
    size_bytes: int | None = None
    built_at: str | None = None


class AgentRegistrationResponse(BaseModel):
    """`token` yalnızca BURADA, kayıt anında bir kez döner — bir daha
    hiçbir API response'unda (GET /api/agents dahil) görünmez."""

    agent_id: UUID
    token: str


class AgentHeartbeatRequest(BaseModel):
    uptime_seconds: float | None = None
    agent_version: str | None = None  # sürüm değişmişse tespit için


class DiskSample(BaseModel):
    device: str
    total_bytes: int | None = None
    used_bytes: int | None = None
    free_bytes: int | None = None
    percent: float | None = None


class NetworkInterfaceSample(BaseModel):
    name: str = Field(max_length=_MAX_NAME_LENGTH)
    # `ip_address`: geriye dönük uyumluluk için korunan TEK/birincil
    # adres (Faz 28'den beri var). `addresses` (Faz 30, additive) —
    # interface'in TÜM IPv4/IPv6 adresleri; `interface_type` (Faz 30) —
    # ethernet/wifi/loopback/docker/vpn/other kaba sınıflandırması
    # (bkz. `apps/agent/agent/collectors/network.py`). İkisi de JSONB
    # sütununda saklandığı için DB migration GEREKTİRMEZ.
    ip_address: str | None = None
    addresses: list[str] = []
    interface_type: str | None = None
    mac_address: str | None = None
    speed_bps: int | None = None
    state: str | None = None
    rx_bytes: int | None = None
    tx_bytes: int | None = None
    rx_errors: int | None = None
    tx_errors: int | None = None


class SessionInfo(BaseModel):
    """Faz 34 — User Sessions Tracking. Windows'ta `quser`, Linux'ta
    `who` çıktısından üretilir (bkz. `apps/agent/agent/platform/
    {windows,linux}.py::list_sessions`). `status` platform-bağımsız
    normalize edilir: `active` | `disconnected` (Linux'ta `who` yalnızca
    o an bağlı oturumları listeler, hep `active`)."""

    username: str = Field(max_length=_MAX_NAME_LENGTH)
    session_name: str | None = None
    status: str | None = None
    logon_time: str | None = None


class AgentTelemetryRequest(BaseModel):
    collected_at: datetime
    schema_version: int = 1
    cpu_percent: float | None = None
    memory_total_bytes: int | None = None
    memory_used_bytes: int | None = None
    memory_percent: float | None = None
    disks: list[DiskSample] = []
    network_interfaces: list[NetworkInterfaceSample] = []
    # Faz 34 — additive. `last_logged_in_user`/`active_sessions_count`
    # agent tarafında `sessions`'tan TÜRETİLİR (bkz. `apps/agent/agent/
    # collectors/sessions.py::summarize_sessions`) — backend burada
    # ayrıca hesaplama YAPMAZ, olduğu gibi saklar.
    sessions: list[SessionInfo] = []
    last_logged_in_user: str | None = None
    active_sessions_count: int | None = None


class HardwareInfo(BaseModel):
    manufacturer: str | None = None
    model: str | None = None
    cpu_model: str | None = None
    cpu_cores: int | None = None
    cpu_logical_processors: int | None = None
    total_memory_bytes: int | None = None


class OSInfo(BaseModel):
    name: str | None = None
    version: str | None = None
    kernel: str | None = None
    architecture: str | None = None
    boot_time: datetime | None = None


class SoftwareItem(BaseModel):
    name: str = Field(max_length=_MAX_NAME_LENGTH)
    version: str | None = None


class ServiceInfo(BaseModel):
    name: str = Field(max_length=_MAX_NAME_LENGTH)
    display_name: str | None = None
    state: str | None = None
    startup_type: str | None = None


class ProcessInfo(BaseModel):
    """Faz 30 — temel process envanteri. Bilinçli olarak dar: yalnızca
    PID/isim/CPU/memory/kullanıcı/durum. Command-line argümanları
    KASITLI olarak burada YOK — credential/token/secret içerebilir,
    agent tarafında toplanmaz, backend'e hiç gönderilmez (bkz.
    `apps/agent/agent/collectors/processes.py` docstring'i)."""

    pid: int
    name: str = Field(max_length=_MAX_NAME_LENGTH)
    cpu_percent: float | None = None
    memory_percent: float | None = None
    username: str | None = None
    status: str | None = None


class AgentInventoryRequest(BaseModel):
    collected_at: datetime
    schema_version: int = 1
    hardware: HardwareInfo | None = None
    os: OSInfo | None = None
    network_interfaces: list[NetworkInterfaceSample] = []
    software: list[SoftwareItem] = []
    services: list[ServiceInfo] = []
    # Faz 30 — additive, ilk sürümde her zaman boş listeyle de
    # çalışır. Süreç listesi genelde büyük olabileceğinden agent
    # tarafında en yoğun N süreçle sınırlanması ÖNERİLİR (bkz. collector
    # docstring'i) — backend burada bir üst sınır ZORLAMAZ, agent'ın
    # kendi disiplinine güvenir (aşırı büyük bir liste yalnızca DB'de
    # daha fazla yer kaplar, bir güvenlik riski oluşturmaz).
    processes: list[ProcessInfo] = []


class AgentSummary(BaseModel):
    """`GET /api/agents` liste öğesi — token DEĞERİ/hash'i hiçbir zaman
    taşınmaz."""

    id: UUID
    hostname: str
    os: AgentOS
    os_version: str | None
    agent_version: str
    local_ip: str | None = None
    asset_id: UUID | None
    status: AgentStatus
    registered_at: datetime
    last_heartbeat_at: datetime | None


class AgentDetail(AgentSummary):
    """`GET /api/agents/{id}` — özet + gerçek en son telemetry/inventory
    (varsa; yoksa `None` — asla uydurulmaz)."""

    fqdn: str | None = None
    architecture: str | None
    mac_address: str | None
    capabilities: list[str]
    revoked_at: datetime | None
    latest_telemetry: AgentTelemetryRequest | None = None
    inventory: AgentInventoryRequest | None = None
