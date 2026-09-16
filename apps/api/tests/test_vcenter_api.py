"""Faz 72 — `/api/vcenter/*` yetkilendirme + orkestrasyon route testleri.
Gerçek bir vCenter'a hiç bağlanılmaz — `app.routes.vcenter`'ın
`service` fonksiyonları patch'lenir."""

from unittest.mock import patch

import pytest

from app.auth.permissions import default_permissions_for_role
from app.auth.security import hash_password
from app.db.users import insert_user, set_permissions
from app.vcenter.client import VCenterConnectError
from app.vcenter.models import DatastoreSummary, HostSummary, VCenterSummary, VmDetail, VmSummary

pytestmark = pytest.mark.anyio


async def _seed_user(isolated_db, *, username, role, permissions=None, password="s3cret-pw!"):
    row = await insert_user(isolated_db, username=username, password_hash=hash_password(password), role=role, full_name=None)
    await set_permissions(isolated_db, row["id"], permissions if permissions is not None else default_permissions_for_role(role))
    return row


async def _login(client, *, username, password="s3cret-pw!") -> str:
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _headers_for(isolated_db, client, *, role, permissions=None, username="vcenter-user") -> dict:
    await _seed_user(isolated_db, username=username, role=role, permissions=permissions)
    token = await _login(client, username=username)
    return {"Authorization": f"Bearer {token}"}


async def _save_config(isolated_db, client, admin_headers) -> None:
    payload = {"host": "vcenter.lab.local", "port": 443, "username": "svc@vsphere.local", "password": "s3cret", "verify_ssl": False}
    response = await client.put("/api/settings/vcenter", headers=admin_headers, json=payload)
    assert response.status_code == 200, response.text


_SAMPLE_VM = VmSummary(id="vm-1", name="web-01", power_state="POWERED_ON", cpu_count=2, memory_mb=4096, ip_address="10.0.1.5", guest_os="ubuntu64Guest")
_SAMPLE_VM_DETAIL = VmDetail(
    id="vm-1", name="web-01", power_state="POWERED_ON", cpu_count=2, memory_mb=4096, ip_address="10.0.1.5",
    guest_os="ubuntu64Guest", guest_hostname="web-01.lab.local",
)
_SAMPLE_HOST = HostSummary(id="host-1", name="esxi-01", connection_state="CONNECTED", power_state="POWERED_ON")
_SAMPLE_SUMMARY = VCenterSummary(
    total_hosts=1, total_vms=1, powered_on_vms=1, total_vcpu_allocated=2, total_memory_gb_allocated=4.0,
    datastores=[DatastoreSummary(id="ds-1", name="datastore1", type="VMFS", capacity_gb=500.0, free_gb=120.0)],
)


async def test_vcenter_view_routes_require_config(isolated_db, client):
    """vCenter hiç yapılandırılmamışsa (bkz. `_clear` — testler arası
    izolasyon) gerçek bir bağlantı denemesi YAPILMADAN dürüst bir 409
    döner."""
    await isolated_db.execute("DELETE FROM vcenter_config")
    headers = await _headers_for(isolated_db, client, role="VIEWER")

    response = await client.get("/api/vcenter/summary", headers=headers)

    assert response.status_code == 409


async def test_vcenter_view_routes_require_vcenter_view_permission(isolated_db, client):
    headers = await _headers_for(isolated_db, client, role="VIEWER", permissions=[])

    response = await client.get("/api/vcenter/vms", headers=headers)

    assert response.status_code == 403


async def test_get_summary_returns_service_result(isolated_db, client):
    admin_headers = await _headers_for(isolated_db, client, role="ADMIN", username="vcenter-admin-1")
    await _save_config(isolated_db, client, admin_headers)
    viewer_headers = await _headers_for(isolated_db, client, role="VIEWER", username="vcenter-viewer-1")

    with patch("app.routes.vcenter.get_summary", return_value=_SAMPLE_SUMMARY):
        response = await client.get("/api/vcenter/summary", headers=viewer_headers)

    assert response.status_code == 200
    assert response.json()["total_vms"] == 1
    assert response.json()["datastores"][0]["name"] == "datastore1"


async def test_list_vms_returns_service_result(isolated_db, client):
    admin_headers = await _headers_for(isolated_db, client, role="ADMIN", username="vcenter-admin-2")
    await _save_config(isolated_db, client, admin_headers)
    viewer_headers = await _headers_for(isolated_db, client, role="VIEWER", username="vcenter-viewer-2")

    with patch("app.routes.vcenter.list_vms", return_value=[_SAMPLE_VM]):
        response = await client.get("/api/vcenter/vms", headers=viewer_headers)

    assert response.status_code == 200
    assert response.json()[0]["ip_address"] == "10.0.1.5"


async def test_get_vm_detail_returns_service_result(isolated_db, client):
    admin_headers = await _headers_for(isolated_db, client, role="ADMIN", username="vcenter-admin-3")
    await _save_config(isolated_db, client, admin_headers)
    viewer_headers = await _headers_for(isolated_db, client, role="VIEWER", username="vcenter-viewer-3")

    with patch("app.routes.vcenter.get_vm_detail", return_value=_SAMPLE_VM_DETAIL):
        response = await client.get("/api/vcenter/vms/vm-1", headers=viewer_headers)

    assert response.status_code == 200
    assert response.json()["guest_hostname"] == "web-01.lab.local"
    # Dürüstlük sınırı: anlık kullanım yüzdesi hiçbir zaman uydurulmaz.
    assert response.json()["cpu_usage_percent"] is None


async def test_list_hosts_returns_service_result(isolated_db, client):
    admin_headers = await _headers_for(isolated_db, client, role="ADMIN", username="vcenter-admin-4")
    await _save_config(isolated_db, client, admin_headers)
    viewer_headers = await _headers_for(isolated_db, client, role="VIEWER", username="vcenter-viewer-4")

    with patch("app.routes.vcenter.list_hosts", return_value=[_SAMPLE_HOST]):
        response = await client.get("/api/vcenter/hosts", headers=viewer_headers)

    assert response.status_code == 200
    assert response.json()[0]["name"] == "esxi-01"


async def test_vcenter_view_route_returns_502_on_connect_error(isolated_db, client):
    admin_headers = await _headers_for(isolated_db, client, role="ADMIN", username="vcenter-admin-5")
    await _save_config(isolated_db, client, admin_headers)
    viewer_headers = await _headers_for(isolated_db, client, role="VIEWER", username="vcenter-viewer-5")

    with patch("app.routes.vcenter.list_vms", side_effect=VCenterConnectError("bağlanılamadı")):
        response = await client.get("/api/vcenter/vms", headers=viewer_headers)

    assert response.status_code == 502


async def test_power_action_requires_vcenter_admin_not_just_view(isolated_db, client):
    """`VCENTER_VIEW`'i olan ama `VCENTER_ADMIN`'i OLMAYAN bir kullanıcı
    görüntüleyebilir ama güç işlemi YAPAMAZ — iki izin GERÇEKTEN ayrı."""
    admin_headers = await _headers_for(isolated_db, client, role="ADMIN", username="vcenter-admin-6")
    await _save_config(isolated_db, client, admin_headers)
    viewer_headers = await _headers_for(isolated_db, client, role="VIEWER", username="vcenter-viewer-6", permissions=["VCENTER_VIEW"])

    response = await client.post("/api/vcenter/vms/vm-1/power", headers=viewer_headers, json={"action": "start"})

    assert response.status_code == 403


async def test_power_action_succeeds_for_vcenter_admin(isolated_db, client):
    admin_headers = await _headers_for(isolated_db, client, role="ADMIN", username="vcenter-admin-7")
    await _save_config(isolated_db, client, admin_headers)

    with patch("app.routes.vcenter.power_action", return_value=None) as mock_power:
        response = await client.post("/api/vcenter/vms/vm-1/power", headers=admin_headers, json={"action": "reset"})

    assert response.status_code == 200
    mock_power.assert_awaited_once()
    assert mock_power.await_args.args[1:] == ("vm-1", "reset")


async def test_power_action_accepts_guest_reboot(isolated_db, client):
    admin_headers = await _headers_for(isolated_db, client, role="ADMIN", username="vcenter-admin-8")
    await _save_config(isolated_db, client, admin_headers)

    with patch("app.routes.vcenter.power_action", return_value=None) as mock_power:
        response = await client.post("/api/vcenter/vms/vm-1/power", headers=admin_headers, json={"action": "guest_reboot"})

    assert response.status_code == 200
    assert mock_power.await_args.args[1:] == ("vm-1", "guest_reboot")
