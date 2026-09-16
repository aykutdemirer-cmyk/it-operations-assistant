"""Faz 76 — `/api/pam/web/*` için gerçek PostgreSQL'e bağlı testler.
Gerçek bir hedef web konsoluna hiçbir testte bağlanılmaz —
`app.routes.pam_web.establish_session` mock'lanır (giriş akışının
KENDİSİ `tests/pam/test_web_console.py`'de izole test ediliyor)."""

from unittest.mock import patch

import pytest

from app.auth.permissions import default_permissions_for_role
from app.auth.security import hash_password
from app.db.assets import upsert_asset
from app.db.users import insert_user, set_permissions
from datetime import datetime, timezone

pytestmark = pytest.mark.anyio


async def _seed_user(isolated_db, *, username, role, password="s3cret-pw!"):
    row = await insert_user(isolated_db, username=username, password_hash=hash_password(password), role=role, full_name=None)
    await set_permissions(isolated_db, row["id"], default_permissions_for_role(role))
    return row


async def _login(client, *, username, password="s3cret-pw!") -> str:
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _seed_asset(isolated_db, **overrides) -> dict:
    defaults = dict(
        ip_address="10.0.9.70",
        hostname="firewalla.example.local",
        mac_address="AA-BB-CC-DD-EE-70",
        vendor="Firewalla",
        device_type="firewall",
        confidence="high",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return await upsert_asset(isolated_db, **defaults)


async def _admin_headers(isolated_db, client, username="web-admin") -> dict:
    await _seed_user(isolated_db, username=username, role="ADMIN")
    token = await _login(client, username=username)
    return {"Authorization": f"Bearer {token}"}


async def _create_rule(isolated_db, client, admin_headers, *, user_id, asset_id, allow_web=True) -> str:
    credential_response = await client.post(
        "/api/pam/vault",
        headers=admin_headers,
        json={"name": f"cred-{asset_id}", "credential_type": "password", "username": "admin", "password": "hunter2"},
    )
    credential_id = credential_response.json()["id"]
    rule_response = await client.post(
        "/api/pam/rules",
        headers=admin_headers,
        json={"user_id": str(user_id), "asset_id": str(asset_id), "credential_id": credential_id, "allow_web": allow_web},
    )
    assert rule_response.status_code == 201, rule_response.text
    return credential_id


async def _configure_profile(client, admin_headers, asset_id) -> None:
    response = await client.put(
        f"/api/pam/web/profiles/{asset_id}",
        headers=admin_headers,
        json={"login_path": "/login", "username_field": "username", "password_field": "password"},
    )
    assert response.status_code == 200, response.text


async def test_web_console_profile_crud_requires_pam_admin(isolated_db, client):
    await _seed_user(isolated_db, username="web-viewer", role="VIEWER")
    token = await _login(client, username="web-viewer")
    headers = {"Authorization": f"Bearer {token}"}
    asset = await _seed_asset(isolated_db)

    response = await client.put(f"/api/pam/web/profiles/{asset['id']}", headers=headers, json={})

    assert response.status_code == 403


async def test_web_console_profile_upsert_and_get(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.71")

    put_response = await client.put(
        f"/api/pam/web/profiles/{asset['id']}",
        headers=headers,
        json={"port": 443, "verify_ssl": False, "login_path": "/login", "username_field": "user", "password_field": "pass"},
    )
    assert put_response.status_code == 200
    assert put_response.json()["username_field"] == "user"

    get_response = await client.get(f"/api/pam/web/profiles/{asset['id']}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["login_path"] == "/login"


async def test_get_web_console_profile_returns_null_when_unconfigured(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.72")

    response = await client.get(f"/api/pam/web/profiles/{asset['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json() is None


async def test_delete_web_console_profile(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.73")
    await _configure_profile(client, headers, asset["id"])

    delete_response = await client.delete(f"/api/pam/web/profiles/{asset['id']}", headers=headers)
    assert delete_response.status_code == 204

    get_response = await client.get(f"/api/pam/web/profiles/{asset['id']}", headers=headers)
    assert get_response.json() is None


async def test_start_session_requires_allow_web_permission_flag(isolated_db, client):
    admin_headers = await _admin_headers(isolated_db, client, username="web-admin2")
    operator = await _seed_user(isolated_db, username="web-op1", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.74")
    await _create_rule(isolated_db, client, admin_headers, user_id=operator["id"], asset_id=asset["id"], allow_web=False)
    await _configure_profile(client, admin_headers, asset["id"])

    operator_token = await _login(client, username="web-op1")
    response = await client.post(
        f"/api/pam/web/{asset['id']}/session", headers={"Authorization": f"Bearer {operator_token}"}
    )

    assert response.status_code == 403


async def test_start_session_returns_409_when_profile_not_configured(isolated_db, client):
    admin_headers = await _admin_headers(isolated_db, client, username="web-admin3")
    operator = await _seed_user(isolated_db, username="web-op2", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.75")
    await _create_rule(isolated_db, client, admin_headers, user_id=operator["id"], asset_id=asset["id"])

    operator_token = await _login(client, username="web-op2")
    response = await client.post(
        f"/api/pam/web/{asset['id']}/session", headers={"Authorization": f"Bearer {operator_token}"}
    )

    assert response.status_code == 409


async def test_start_session_success_creates_session_log_with_protocol_web(isolated_db, client):
    admin_headers = await _admin_headers(isolated_db, client, username="web-admin4")
    operator = await _seed_user(isolated_db, username="web-op3", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.76")
    await _create_rule(isolated_db, client, admin_headers, user_id=operator["id"], asset_id=asset["id"])
    await _configure_profile(client, admin_headers, asset["id"])

    operator_token = await _login(client, username="web-op3")
    with patch("app.routes.pam_web.establish_session", return_value={"session": "abc"}):
        response = await client.post(
            f"/api/pam/web/{asset['id']}/session", headers={"Authorization": f"Bearer {operator_token}"}
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["proxy_url"] == f"/api/pam/web/proxy/{body['session_id']}/"

    log_row = await isolated_db.fetchrow("SELECT protocol FROM pam_session_logs WHERE id = $1", body["session_id"])
    assert log_row["protocol"] == "web"


async def test_start_session_returns_502_on_connect_error(isolated_db, client):
    from app.pam.web_console import WebConsoleConnectError

    admin_headers = await _admin_headers(isolated_db, client, username="web-admin5")
    operator = await _seed_user(isolated_db, username="web-op4", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.77")
    await _create_rule(isolated_db, client, admin_headers, user_id=operator["id"], asset_id=asset["id"])
    await _configure_profile(client, admin_headers, asset["id"])

    operator_token = await _login(client, username="web-op4")
    with patch("app.routes.pam_web.establish_session", side_effect=WebConsoleConnectError("bağlanılamadı")):
        response = await client.post(
            f"/api/pam/web/{asset['id']}/session", headers={"Authorization": f"Bearer {operator_token}"}
        )

    assert response.status_code == 502


async def test_proxy_route_returns_404_for_unknown_session(isolated_db, client):
    headers = await _admin_headers(isolated_db, client, username="web-admin6")

    response = await client.get("/api/pam/web/proxy/11111111-1111-1111-1111-111111111111/", headers=headers)

    assert response.status_code == 404
