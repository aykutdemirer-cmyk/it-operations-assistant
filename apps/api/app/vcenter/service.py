"""Faz 72 — vCenter orkestrasyon katmanı. `client.py`'nin ham REST
çağrılarını gerçek envanter/özet/güç işlemlerine dönüştürür. Route
katmanı (`app/routes/vcenter.py`) yalnızca burayı çağırır, HTTP
detayına (`client.py`) hiç dokunmaz."""

import asyncio
import logging

from app.vcenter.client import VCenterConnectError, VCenterConnectionParams, VCenterSession
from app.vcenter.models import DatastoreSummary, HostSummary, PowerAction, VCenterSummary, VmDetail, VmSummary

logger = logging.getLogger(__name__)

# `poller.py::SNMP_MAX_CONCURRENCY` ile AYNI ilke — guest/identity'yi
# tüm VM'ler için TEK TEK sırayla sormak yavaş olurdu, sınırsız paralel
# ise vCenter'a gereksiz yük bindirir.
_GUEST_IDENTITY_CONCURRENCY = 8


async def test_connection(params: VCenterConnectionParams) -> None:
    """Başarısızlıkta `VCenterConnectError` fırlatır — çağıran taraf
    (route) bunu dürüst bir `success=false` sonucuna çevirir (SNMP/LDAP
    "Bağlantıyı Test Et" ile aynı ilke)."""
    async with VCenterSession(params):
        pass


class _GuestIdentity:
    __slots__ = ("ip_address", "full_name")

    def __init__(self, ip_address: str | None, full_name: str | None):
        self.ip_address = ip_address
        self.full_name = full_name


def _extract_full_name(raw_full_name: object) -> str | None:
    """`guest/identity.full_name` düz bir string DEĞİL — vSphere REST
    API'sinin `LocalizableMessage` yapısı (`{id, default_message,
    args, localized}`) olarak gelir (GERÇEK bir vCenter'a karşı canlı
    denemede bulunan bir hata — vCLS/CRX gibi özel sistem VM'lerinde
    kesin olarak bu şekilde, normal guest'lerde de aynı sözleşme
    olabilir). `localized` varsa (sunucunun kendi diline çevrilmiş) onu,
    yoksa `default_message`'ı kullan — ikisi de yoksa dürüstçe `None`."""
    if isinstance(raw_full_name, str):
        return raw_full_name
    if isinstance(raw_full_name, dict):
        return raw_full_name.get("localized") or raw_full_name.get("default_message")
    return None


async def _fetch_guest_identity(session: VCenterSession, vm_id: str, semaphore: asyncio.Semaphore) -> tuple[str, _GuestIdentity]:
    async with semaphore:
        try:
            identity = await session.get(f"/vcenter/vm/{vm_id}/guest/identity")
        except VCenterConnectError:
            # VMware Tools çalışmıyor/kurulu değil — 404/503 GERÇEK bir
            # hata değil, dürüstçe "bilinmiyor" anlamına gelir.
            return vm_id, _GuestIdentity(None, None)
        if isinstance(identity, dict):
            # `full_name` — Tools'un raporladığı GERÇEK, okunabilir OS adı
            # (ör. "Microsoft Windows Server 2022") — statik `guest_OS`
            # tanımlayıcısından (ör. `windows9Server64Guest`) daha doğru.
            return vm_id, _GuestIdentity(identity.get("ip_address"), _extract_full_name(identity.get("full_name")))
        return vm_id, _GuestIdentity(None, None)


def _to_vm_summary(raw: dict, identity_by_vm: dict[str, _GuestIdentity]) -> VmSummary:
    vm_id = raw["vm"]
    identity = identity_by_vm.get(vm_id, _GuestIdentity(None, None))
    return VmSummary(
        id=vm_id,
        name=raw.get("name", vm_id),
        power_state=raw.get("power_state", "UNKNOWN"),
        cpu_count=raw.get("cpu_count"),
        memory_mb=raw.get("memory_size_MiB"),
        ip_address=identity.ip_address,
        # Tools'tan gerçek ad geldiyse onu kullan, yoksa statik config
        # tanımlayıcısına dürüstçe düş — YENİ bir alan EKLENMEDİ.
        guest_os=identity.full_name or raw.get("guest_OS"),
    )


async def list_vms(params: VCenterConnectionParams) -> list[VmSummary]:
    async with VCenterSession(params) as session:
        raw_vms = await session.get("/vcenter/vm")
        if not isinstance(raw_vms, list):
            return []

        semaphore = asyncio.Semaphore(_GUEST_IDENTITY_CONCURRENCY)
        identity_results = await asyncio.gather(*(_fetch_guest_identity(session, vm["vm"], semaphore) for vm in raw_vms))
        identity_by_vm = dict(identity_results)

        return [_to_vm_summary(vm, identity_by_vm) for vm in raw_vms]


async def get_vm_detail(params: VCenterConnectionParams, vm_id: str) -> VmDetail:
    async with VCenterSession(params) as session:
        raw = await session.get(f"/vcenter/vm/{vm_id}")
        if not isinstance(raw, dict):
            raise VCenterConnectError(f"VM bulunamadı: {vm_id}")

        ip_address = None
        guest_hostname = None
        guest_full_name = None
        try:
            identity = await session.get(f"/vcenter/vm/{vm_id}/guest/identity")
            if isinstance(identity, dict):
                ip_address = identity.get("ip_address")
                guest_hostname = identity.get("host_name")
                guest_full_name = _extract_full_name(identity.get("full_name"))
        except VCenterConnectError:
            # VMware Tools çalışmıyor/kurulu değil — dürüstçe "bilinmiyor".
            pass

        cpu = raw.get("cpu") or {}
        memory = raw.get("memory") or {}
        return VmDetail(
            id=vm_id,
            name=raw.get("name", vm_id),
            power_state=raw.get("power_state", "UNKNOWN"),
            cpu_count=cpu.get("count"),
            memory_mb=memory.get("size_MiB"),
            ip_address=ip_address,
            guest_os=guest_full_name or raw.get("guest_OS"),
            guest_hostname=guest_hostname,
        )


async def list_hosts(params: VCenterConnectionParams) -> list[HostSummary]:
    async with VCenterSession(params) as session:
        raw_hosts = await session.get("/vcenter/host")
        if not isinstance(raw_hosts, list):
            return []
        return [
            HostSummary(
                id=h["host"],
                name=h.get("name", h["host"]),
                connection_state=h.get("connection_state", "UNKNOWN"),
                power_state=h.get("power_state", "UNKNOWN"),
            )
            for h in raw_hosts
        ]


async def list_datastores(params: VCenterConnectionParams) -> list[DatastoreSummary]:
    async with VCenterSession(params) as session:
        raw = await session.get("/vcenter/datastore")
        if not isinstance(raw, list):
            return []
        result = []
        for ds in raw:
            capacity_bytes = ds.get("capacity") or 0
            free_bytes = ds.get("free_space") or 0
            result.append(
                DatastoreSummary(
                    id=ds["datastore"],
                    name=ds.get("name", ds["datastore"]),
                    type=ds.get("type", "UNKNOWN"),
                    capacity_gb=round(capacity_bytes / (1024**3), 2),
                    free_gb=round(free_bytes / (1024**3), 2),
                )
            )
        return result


async def get_summary(params: VCenterConnectionParams) -> VCenterSummary:
    """Ayrı ayrı 3 uç noktayı (`/vm`, `/host`, `/datastore`) tek bir
    vCenter oturumu İÇİNDE değil, `list_vms`/`list_hosts`/`list_
    datastores`'un HER BİRİ kendi oturumunu açtığı için art arda 3 ayrı
    oturum açılır — bu fazın kapsamında (istek-anlık, arka plan
    worker'ı YOK) kabul edilebilir bir ödünleşim; VM sayısı arttıkça
    (guest/identity N+1 çağrıları) bir sonraki adım paylaşımlı tek
    oturum + önbellek olur (bkz. docs/roadmap.md Faz 72 kapsam dışı)."""
    vms = await list_vms(params)
    hosts = await list_hosts(params)
    datastores = await list_datastores(params)

    return VCenterSummary(
        total_hosts=len(hosts),
        total_vms=len(vms),
        powered_on_vms=sum(1 for vm in vms if vm.power_state == "POWERED_ON"),
        total_vcpu_allocated=sum(vm.cpu_count or 0 for vm in vms),
        total_memory_gb_allocated=round(sum((vm.memory_mb or 0) for vm in vms) / 1024, 2),
        datastores=datastores,
    )


async def power_action(params: VCenterConnectionParams, vm_id: str, action: PowerAction) -> None:
    async with VCenterSession(params) as session:
        if action == "guest_reboot":
            # vCenter REST'in AYRI "guest OS işlemleri" uç noktası — sert
            # `power/reset`'ten FARKLI, VMware Tools üzerinden graceful
            # bir yeniden başlatma ister (Tools yoksa GERÇEK bir hata
            # olarak dürüstçe yukarı fırlar, sessizce reset'e düşülmez).
            await session.post(f"/vcenter/vm/{vm_id}/guest/power?action=reboot")
        else:
            await session.post(f"/vcenter/vm/{vm_id}/power/{action}")
