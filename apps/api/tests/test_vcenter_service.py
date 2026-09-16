"""Faz 72 — `app/vcenter/service.py` orkestrasyon testleri. Gerçek bir
vCenter'a hiç bağlanılmaz — `app.vcenter.service.VCenterSession`
sahte bir async context manager ile patch'lenir (`get`/`post` çağrılarının
ne döndürdüğü test başına kontrol edilir)."""

from unittest.mock import patch

import pytest

from app.vcenter.client import VCenterConnectError
from app.vcenter import service

pytestmark = pytest.mark.anyio

_PARAMS = {
    "host": "vcenter.lab.local",
    "port": 443,
    "username": "admin@vsphere.local",
    "password": "s3cret",
    "verify_ssl": False,
}


class _FakeSession:
    """`get`/`post` çağrılarını `responses` sözlüğünden (path → dönüş
    değeri veya exception) çözen sahte `VCenterSession`."""

    def __init__(self, responses: dict):
        self._responses = responses
        self.posted_paths: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return None

    async def get(self, path, *, params=None):
        result = self._responses.get(path, [])
        if isinstance(result, Exception):
            raise result
        return result

    async def post(self, path, *, json=None):
        self.posted_paths.append(path)
        result = self._responses.get(path)
        if isinstance(result, Exception):
            raise result
        return result


def _patch_session(responses: dict):
    return patch("app.vcenter.service.VCenterSession", return_value=_FakeSession(responses))


async def test_list_vms_maps_fields_and_resolves_guest_ip():
    responses = {
        "/vcenter/vm": [
            {"vm": "vm-1", "name": "web-01", "power_state": "POWERED_ON", "cpu_count": 2, "memory_size_MiB": 4096},
        ],
        "/vcenter/vm/vm-1/guest/identity": {"ip_address": "10.0.1.5", "host_name": "web-01.lab.local"},
    }
    with _patch_session(responses):
        vms = await service.list_vms(_PARAMS)

    assert len(vms) == 1
    vm = vms[0]
    assert vm.id == "vm-1"
    assert vm.name == "web-01"
    assert vm.power_state == "POWERED_ON"
    assert vm.cpu_count == 2
    assert vm.memory_mb == 4096
    assert vm.ip_address == "10.0.1.5"


async def test_list_vms_ip_is_none_when_guest_tools_not_running():
    """VMware Tools çalışmıyorsa `guest/identity` 404 döner — bu bir
    GERÇEK bağlantı hatası DEĞİL, dürüstçe `ip_address=None` anlamına
    gelir (uydurulmaz)."""
    responses = {
        "/vcenter/vm": [{"vm": "vm-2", "name": "no-tools", "power_state": "POWERED_OFF", "cpu_count": 1, "memory_size_MiB": 1024}],
        "/vcenter/vm/vm-2/guest/identity": VCenterConnectError("HTTP 404"),
    }
    with _patch_session(responses):
        vms = await service.list_vms(_PARAMS)

    assert vms[0].ip_address is None


async def test_list_vms_prefers_real_guest_full_name_over_static_config_os():
    """Faz 73 — `guest/identity.full_name` (VMware Tools'un raporladığı
    GERÇEK ad) statik `guest_OS` config tanımlayıcısına TERCİH edilir."""
    responses = {
        "/vcenter/vm": [
            {"vm": "vm-1", "name": "web-01", "power_state": "POWERED_ON", "cpu_count": 2, "memory_size_MiB": 4096, "guest_OS": "windows9Server64Guest"},
        ],
        "/vcenter/vm/vm-1/guest/identity": {"ip_address": "10.0.1.5", "full_name": "Microsoft Windows Server 2022"},
    }
    with _patch_session(responses):
        vms = await service.list_vms(_PARAMS)

    assert vms[0].guest_os == "Microsoft Windows Server 2022"


async def test_list_vms_extracts_full_name_from_localizable_message_object():
    """Faz 73 bugfix — GERÇEK bir vCenter'a karşı canlı denemede bulunan
    bir hata: `full_name` düz bir string DEĞİL, vSphere REST API'sinin
    `LocalizableMessage` yapısı (`{id, default_message, args}`) olarak
    geliyor — özellikle vCLS/CRX gibi özel sistem VM'lerinde. Bu tip
    kontrolü olmadan `VmSummary` (Pydantic `str` alanı) bir dict ile
    ValidationError'a düşüp TÜM `/api/vcenter/vms` isteğini 500'e
    çeviriyordu."""
    responses = {
        "/vcenter/vm": [{"vm": "vm-sys", "name": "vCLS-abc", "power_state": "POWERED_ON", "cpu_count": 1, "memory_size_MiB": 128}],
        "/vcenter/vm/vm-sys/guest/identity": {
            "full_name": {"args": [], "default_message": "VMware Photon OS (64-bit)", "id": "vmw.acce.vmotos.crxSys1Guest.label"},
        },
    }
    with _patch_session(responses):
        vms = await service.list_vms(_PARAMS)

    assert vms[0].guest_os == "VMware Photon OS (64-bit)"


async def test_list_vms_falls_back_to_static_guest_os_without_tools():
    responses = {
        "/vcenter/vm": [
            {"vm": "vm-1", "name": "web-01", "power_state": "POWERED_ON", "cpu_count": 2, "memory_size_MiB": 4096, "guest_OS": "windows9Server64Guest"},
        ],
        "/vcenter/vm/vm-1/guest/identity": VCenterConnectError("HTTP 404"),
    }
    with _patch_session(responses):
        vms = await service.list_vms(_PARAMS)

    assert vms[0].guest_os == "windows9Server64Guest"


async def test_list_hosts_maps_fields():
    responses = {
        "/vcenter/host": [
            {"host": "host-1", "name": "esxi-01.lab.local", "connection_state": "CONNECTED", "power_state": "POWERED_ON"},
        ],
    }
    with _patch_session(responses):
        hosts = await service.list_hosts(_PARAMS)

    assert hosts[0].id == "host-1"
    assert hosts[0].name == "esxi-01.lab.local"


async def test_list_datastores_converts_bytes_to_gb():
    responses = {
        "/vcenter/datastore": [
            {"datastore": "ds-1", "name": "datastore1", "type": "VMFS", "capacity": 1024**3 * 500, "free_space": 1024**3 * 120},
        ],
    }
    with _patch_session(responses):
        datastores = await service.list_datastores(_PARAMS)

    assert datastores[0].capacity_gb == 500.0
    assert datastores[0].free_gb == 120.0


async def test_get_summary_aggregates_vms_hosts_datastores():
    vm_responses = {
        "/vcenter/vm": [
            {"vm": "vm-1", "name": "a", "power_state": "POWERED_ON", "cpu_count": 2, "memory_size_MiB": 2048},
            {"vm": "vm-2", "name": "b", "power_state": "POWERED_OFF", "cpu_count": 4, "memory_size_MiB": 4096},
        ],
        "/vcenter/vm/vm-1/guest/identity": VCenterConnectError("404"),
        "/vcenter/vm/vm-2/guest/identity": VCenterConnectError("404"),
        "/vcenter/host": [{"host": "host-1", "name": "esxi-01", "connection_state": "CONNECTED", "power_state": "POWERED_ON"}],
        "/vcenter/datastore": [],
    }
    with _patch_session(vm_responses):
        summary = await service.get_summary(_PARAMS)

    assert summary.total_hosts == 1
    assert summary.total_vms == 2
    assert summary.powered_on_vms == 1
    assert summary.total_vcpu_allocated == 6
    assert summary.total_memory_gb_allocated == 6.0


async def test_get_vm_detail_maps_allocation_and_guest_identity_once():
    responses = {
        "/vcenter/vm/vm-1": {"name": "web-01", "power_state": "POWERED_ON", "cpu": {"count": 2}, "memory": {"size_MiB": 4096}},
        "/vcenter/vm/vm-1/guest/identity": {"ip_address": "10.0.1.5", "host_name": "web-01.lab.local"},
    }
    with _patch_session(responses):
        detail = await service.get_vm_detail(_PARAMS, "vm-1")

    assert detail.cpu_count == 2
    assert detail.memory_mb == 4096
    assert detail.ip_address == "10.0.1.5"
    assert detail.guest_hostname == "web-01.lab.local"
    # Faz 72 dürüstlük sınırı: anlık kullanım yüzdesi REST inventory
    # API'sinde yok — uydurulmadı, her zaman None.
    assert detail.cpu_usage_percent is None
    assert detail.memory_usage_percent is None


async def test_get_vm_detail_raises_when_vm_not_found():
    with _patch_session({"/vcenter/vm/missing": None}):
        with pytest.raises(VCenterConnectError, match="bulunamadı"):
            await service.get_vm_detail(_PARAMS, "missing")


async def test_power_action_posts_to_correct_path():
    fake = _FakeSession({"/vcenter/vm/vm-1/power/start": None})
    with patch("app.vcenter.service.VCenterSession", return_value=fake):
        await service.power_action(_PARAMS, "vm-1", "start")

    assert fake.posted_paths == ["/vcenter/vm/vm-1/power/start"]


async def test_power_action_guest_reboot_uses_separate_guest_power_endpoint():
    """Faz 73 — `guest_reboot` sert `power/reset`'ten FARKLI, vCenter'ın
    ayrı "guest OS işlemleri" uç noktasını (VMware Tools üzerinden
    graceful) çağırır."""
    fake = _FakeSession({"/vcenter/vm/vm-1/guest/power?action=reboot": None})
    with patch("app.vcenter.service.VCenterSession", return_value=fake):
        await service.power_action(_PARAMS, "vm-1", "guest_reboot")

    assert fake.posted_paths == ["/vcenter/vm/vm-1/guest/power?action=reboot"]


async def test_test_connection_raises_on_connect_error():
    class _FailingSession:
        async def __aenter__(self):
            raise VCenterConnectError("bağlanılamadı")

        async def __aexit__(self, *exc_info):
            return None

    with patch("app.vcenter.service.VCenterSession", return_value=_FailingSession()):
        with pytest.raises(VCenterConnectError):
            await service.test_connection(_PARAMS)


async def test_test_connection_succeeds_silently():
    with _patch_session({}):
        await service.test_connection(_PARAMS)  # exception fırlatmazsa başarılı
