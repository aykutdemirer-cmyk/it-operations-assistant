"""Faz 72 — vCenter/vSphere Pydantic modelleri. `app/routes/vcenter.py`
(envanter/güç) ve `app/routes/vcenter_settings.py` (yapılandırma) ile
birebir."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

PowerState = Literal["POWERED_ON", "POWERED_OFF", "SUSPENDED", "UNKNOWN"]
PowerAction = Literal["start", "stop", "reset", "guest_reboot"]


class VCenterConfigRequest(BaseModel):
    host: str
    port: int = 443
    username: str
    # Boş bırakılırsa (PUT'ta) kayıtlı şifreli parola korunur — `app/
    # routes/ldap_settings.py::_resolve_encrypted_bind_password` ile
    # AYNI ilke.
    password: str | None = None
    verify_ssl: bool = False


class VCenterConfigResponse(BaseModel):
    host: str
    port: int
    username: str
    verify_ssl: bool
    last_test_status: str | None
    last_test_error: str | None
    last_test_at: datetime | None
    updated_at: datetime


class VCenterTestResult(BaseModel):
    success: bool
    message: str


class VmSummary(BaseModel):
    id: str
    name: str
    power_state: PowerState
    # Kaynak TAHSİSİ — vCenter REST Inventory API'sinin verdiği gerçek
    # değer. Anlık kullanım YÜZDESİ bu API'de yok (bkz. docs/roadmap.md
    # Faz 72 — Performance Manager/SOAP gerektirir).
    cpu_count: int | None
    memory_mb: int | None
    # `guest/identity` uç noktasından — yalnızca VMware Tools çalışıyorsa
    # dolu; yoksa dürüstçe None (uydurulmadı).
    ip_address: str | None
    guest_os: str | None


class VmDetail(VmSummary):
    guest_hostname: str | None
    # Anlık CPU/RAM tüketim yüzdesi — bu fazda bilinçli olarak yok
    # (bkz. VmSummary docstring'i), alan burada da her zaman None.
    cpu_usage_percent: float | None = None
    memory_usage_percent: float | None = None


class HostSummary(BaseModel):
    id: str
    name: str
    connection_state: str
    power_state: str


class DatastoreSummary(BaseModel):
    id: str
    name: str
    type: str
    capacity_gb: float
    free_gb: float


class VCenterSummary(BaseModel):
    total_hosts: int
    total_vms: int
    powered_on_vms: int
    total_vcpu_allocated: int
    total_memory_gb_allocated: float
    datastores: list[DatastoreSummary]


class PowerActionRequest(BaseModel):
    action: PowerAction
