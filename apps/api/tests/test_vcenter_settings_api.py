"""Faz 72 — `/api/settings/vcenter/*` için gerçek PostgreSQL'e bağlı
testler (bkz. kök `conftest.py::isolated_db`). Gerçek bir vCenter'a
hiçbir testte bağlanılmaz — `app.routes.vcenter_settings.test_connection`
mock'lanır (bkz. `tests/test_vcenter_service.py` için `httpx` seviyesinde
mock'lanan ayrı testler)."""

from unittest.mock import patch

import pytest

from app.auth.permissions import default_permissions_for_role
from app.auth.security import hash_password
from app.db.users import insert_user, set_permissions
from app.vcenter.client import VCenterConnectError

pytestmark = pytest.mark.anyio


async def _seed_user(isolated_db, *, username, role, password="s3cret-pw!"):
    row = await insert_user(isolated_db, username=username, password_hash=hash_password(password), role=role, full_name=None)
    await set_permissions(isolated_db, row["id"], default_permissions_for_role(role))
    return row


async def _login(client, *, username, password="s3cret-pw!") -> str:
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _admin_headers(isolated_db, client, username="vcenter-admin") -> dict:
    await _seed_user(isolated_db, username=username, role="ADMIN")
    token = await _login(client, username=username)
    return {"Authorization": f"Bearer {token}"}


async def _clear_saved_config(isolated_db) -> None:
    """`vcenter_config` tek-satırlı (id=1) — `ldap_config`'in aynı
    izolasyon notuyla AYNI gerekçe: gerçek, kalıcı bir satır varsa bu
    testin kendi (rollback edilen) transaction'ı içinde temizlenmeli."""
    await isolated_db.execute("DELETE FROM vcenter_config")


def _config_payload(**overrides) -> dict:
    payload = {
        "host": "vcenter.lab.local",
        "port": 443,
        "username": "svc-vcenter@vsphere.local",
        "password": "s3cret",
        "verify_ssl": False,
    }
    payload.update(overrides)
    return payload


async def test_put_vcenter_config_without_password_on_first_save_returns_422(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await _clear_saved_config(isolated_db)

    response = await client.put("/api/settings/vcenter", headers=headers, json=_config_payload(password=None))

    assert response.status_code == 422


async def test_put_vcenter_config_with_empty_password_keeps_existing_encrypted_password(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await client.put("/api/settings/vcenter", headers=headers, json=_config_payload(password="ilk-parola"))

    response = await client.put("/api/settings/vcenter", headers=headers, json=_config_payload(password=None, port=8443))

    assert response.status_code == 200
    assert response.json()["port"] == 8443
    row = await isolated_db.fetchrow("SELECT encrypted_password FROM vcenter_config WHERE id = 1")
    from app.pam.vault import decrypt_payload

    assert decrypt_payload(row["encrypted_password"])["password"] == "ilk-parola"


async def test_put_vcenter_config_never_returns_password_in_response(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    response = await client.put("/api/settings/vcenter", headers=headers, json=_config_payload())

    assert "password" not in response.json()
    assert response.json()["username"] == "svc-vcenter@vsphere.local"


async def test_get_vcenter_config_returns_null_when_unconfigured(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await _clear_saved_config(isolated_db)

    response = await client.get("/api/settings/vcenter", headers=headers)

    assert response.status_code == 200
    assert response.json() is None


async def test_vcenter_settings_routes_require_vcenter_admin(isolated_db, client):
    await _seed_user(isolated_db, username="vcenter-viewer", role="VIEWER")
    token = await _login(client, username="vcenter-viewer")
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get("/api/settings/vcenter", headers=headers)

    assert response.status_code == 403


async def test_test_connection_returns_success_true_without_persisting_config(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await _clear_saved_config(isolated_db)

    with patch("app.routes.vcenter_settings.test_connection", return_value=None):
        response = await client.post("/api/settings/vcenter/test", headers=headers, json=_config_payload())

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Bağlantı başarılı"}
    row = await isolated_db.fetchrow("SELECT * FROM vcenter_config WHERE id = 1")
    assert row is None


async def test_test_connection_returns_success_false_on_connect_error(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await _clear_saved_config(isolated_db)

    with patch("app.routes.vcenter_settings.test_connection", side_effect=VCenterConnectError("bağlanılamadı")):
        response = await client.post("/api/settings/vcenter/test", headers=headers, json=_config_payload())

    body = response.json()
    assert body["success"] is False
    assert "bağlanılamadı" in body["message"]


async def test_test_connection_without_password_uses_saved_password(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await client.put("/api/settings/vcenter", headers=headers, json=_config_payload(password="kayitli-parola"))

    captured = {}

    async def _fake_test_connection(params):
        captured.update(params)

    with patch("app.routes.vcenter_settings.test_connection", side_effect=_fake_test_connection):
        response = await client.post("/api/settings/vcenter/test", headers=headers, json=_config_payload(password=None))

    assert response.status_code == 200
    assert captured["password"] == "kayitli-parola"


async def test_test_connection_without_password_and_no_saved_config_returns_422(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await _clear_saved_config(isolated_db)

    response = await client.post("/api/settings/vcenter/test", headers=headers, json=_config_payload(password=None))

    assert response.status_code == 422
