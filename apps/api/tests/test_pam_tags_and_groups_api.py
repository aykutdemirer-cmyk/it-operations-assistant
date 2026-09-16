"""Faz 55 — `/api/pam/tags`, `/api/pam/server-groups` CRUD + üyelik
route'ları, VE bunların `pam_access_rules`'ta bir cihaz hedefi olarak
gerçek SSH/RDP yetkilendirmesinde kullanılabildiğini doğrulayan
testler. Gerçek PostgreSQL'e bağlı (`isolated_db`), gerçek bir SSH/RDP
bağlantısı hiçbir testte açılmaz."""

from datetime import datetime, timezone

import pytest

from app.auth.permissions import default_permissions_for_role
from app.auth.security import hash_password
from app.db.assets import upsert_asset
from app.db.users import insert_user, set_permissions

pytestmark = pytest.mark.anyio


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _seed_user(isolated_db, *, username, role, password="s3cret-pw!"):
    row = await insert_user(isolated_db, username=username, password_hash=hash_password(password), role=role, full_name=None)
    await set_permissions(isolated_db, row["id"], default_permissions_for_role(role))
    return row


async def _login(client, *, username, password="s3cret-pw!") -> str:
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _admin_headers(isolated_db, client, username="tags-admin") -> dict:
    await _seed_user(isolated_db, username=username, role="ADMIN")
    token = await _login(client, username=username)
    return {"Authorization": f"Bearer {token}"}


async def _seed_asset(isolated_db, **overrides) -> dict:
    defaults = dict(
        ip_address="10.0.11.10",
        hostname="tag-target.example.local",
        mac_address="AA-BB-CC-DD-EE-60",
        vendor="Dell Inc.",
        device_type="server",
        confidence="high",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )
    defaults.update(overrides)
    return await upsert_asset(isolated_db, **defaults)


async def _create_credential(client, headers) -> str:
    response = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": f"cred-{_now().timestamp()}", "credential_type": "password", "username": "root", "password": "x"},
    )
    return response.json()["id"]


# ---- Tags CRUD --------------------------------------------------------------


async def test_create_and_list_tag(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)

    create_response = await client.post("/api/pam/tags", headers=headers, json={"name": "Production"})
    assert create_response.status_code == 201
    assert create_response.json()["name"] == "Production"

    list_response = await client.get("/api/pam/tags", headers=headers)
    assert list_response.status_code == 200
    assert "Production" in [t["name"] for t in list_response.json()]


async def test_assign_and_list_tag_assets(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    asset = await _seed_asset(isolated_db, ip_address="10.0.11.11", hostname="tagged1.example.local")
    tag_id = (await client.post("/api/pam/tags", headers=headers, json={"name": "Linux"})).json()["id"]

    assign_response = await client.put(f"/api/pam/tags/{tag_id}/assets/{asset['id']}", headers=headers)
    assert assign_response.status_code == 204

    assets_response = await client.get(f"/api/pam/tags/{tag_id}/assets", headers=headers)
    assert assets_response.status_code == 200
    assert [a["hostname"] for a in assets_response.json()] == ["tagged1.example.local"]


async def test_delete_tag_in_use_returns_409(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="tag-op1", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.11.12")
    tag_id = (await client.post("/api/pam/tags", headers=headers, json={"name": "Finance"})).json()["id"]
    credential_id = await _create_credential(client, headers)
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={"user_id": str(operator["id"]), "tag_id": tag_id, "credential_id": credential_id, "allow_ssh": True},
    )

    response = await client.delete(f"/api/pam/tags/{tag_id}", headers=headers)

    assert response.status_code == 409


# ---- Server Groups CRUD ------------------------------------------------------


async def test_create_update_and_delete_server_group(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)

    create_response = await client.post(
        "/api/pam/server-groups", headers=headers, json={"name": "Linux Sunucuları", "description": "Tüm Linux hostlar"}
    )
    assert create_response.status_code == 201
    group_id = create_response.json()["id"]

    update_response = await client.put(
        f"/api/pam/server-groups/{group_id}", headers=headers, json={"description": "Güncellendi"}
    )
    assert update_response.status_code == 200
    assert update_response.json()["description"] == "Güncellendi"
    assert update_response.json()["name"] == "Linux Sunucuları"

    delete_response = await client.delete(f"/api/pam/server-groups/{group_id}", headers=headers)
    assert delete_response.status_code == 204


async def test_add_and_list_group_members(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    asset = await _seed_asset(isolated_db, ip_address="10.0.11.13", hostname="member1.example.local")
    group_id = (await client.post("/api/pam/server-groups", headers=headers, json={"name": "DB Sunucuları"})).json()["id"]

    add_response = await client.put(f"/api/pam/server-groups/{group_id}/assets/{asset['id']}", headers=headers)
    assert add_response.status_code == 204

    members_response = await client.get(f"/api/pam/server-groups/{group_id}/assets", headers=headers)
    assert [a["hostname"] for a in members_response.json()] == ["member1.example.local"]

    remove_response = await client.delete(f"/api/pam/server-groups/{group_id}/assets/{asset['id']}", headers=headers)
    assert remove_response.status_code == 204
    members_after = await client.get(f"/api/pam/server-groups/{group_id}/assets", headers=headers)
    assert members_after.json() == []


async def test_delete_group_in_use_returns_409(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="group-op1", role="OPERATOR")
    group_id = (await client.post("/api/pam/server-groups", headers=headers, json={"name": "Kritik Sunucular"})).json()["id"]
    credential_id = await _create_credential(client, headers)
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "user_id": str(operator["id"]),
            "server_group_id": group_id,
            "credential_id": credential_id,
            "allow_rdp": True,
        },
    )

    response = await client.delete(f"/api/pam/server-groups/{group_id}", headers=headers)

    assert response.status_code == 409


# ---- Rule device-target XOR + gerçek yetkilendirme --------------------------


async def test_create_rule_rejects_multiple_device_targets(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="xor-op1", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.11.14")
    tag_id = (await client.post("/api/pam/tags", headers=headers, json={"name": "XorTag"})).json()["id"]
    credential_id = await _create_credential(client, headers)

    response = await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "user_id": str(operator["id"]),
            "asset_id": str(asset["id"]),
            "tag_id": tag_id,
            "credential_id": credential_id,
            "allow_ssh": True,
        },
    )

    assert response.status_code == 422


async def test_create_rule_rejects_zero_device_targets(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="xor-op2", role="OPERATOR")
    credential_id = await _create_credential(client, headers)

    response = await client.post(
        "/api/pam/rules",
        headers=headers,
        json={"user_id": str(operator["id"]), "credential_id": credential_id, "allow_ssh": True},
    )

    assert response.status_code == 422


async def test_ssh_authorization_via_tag_rule(isolated_db, client):
    from app.pam.service import authorize_ssh_session

    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="tag-auth-op", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.11.15", hostname="tag-auth-target.example.local")
    tag_id = (await client.post("/api/pam/tags", headers=headers, json={"name": "TagAuth"})).json()["id"]
    await client.put(f"/api/pam/tags/{tag_id}/assets/{asset['id']}", headers=headers)
    credential_id = await _create_credential(client, headers)
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={"user_id": str(operator["id"]), "tag_id": tag_id, "credential_id": credential_id, "allow_ssh": True},
    )

    username, payload, max_duration, cred_id = await authorize_ssh_session(
        isolated_db, user_id=operator["id"], asset_id=asset["id"]
    )

    assert username == "root"
    assert str(cred_id) == credential_id


async def test_rdp_authorization_via_server_group_rule(isolated_db, client):
    from app.pam.service import authorize_rdp_session

    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="group-auth-op", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.11.16", hostname="group-auth-target.example.local")
    group_id = (await client.post("/api/pam/server-groups", headers=headers, json={"name": "GroupAuth"})).json()["id"]
    await client.put(f"/api/pam/server-groups/{group_id}/assets/{asset['id']}", headers=headers)
    credential_id = await _create_credential(client, headers)
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "user_id": str(operator["id"]),
            "server_group_id": group_id,
            "credential_id": credential_id,
            "allow_rdp": True,
        },
    )

    authorization = await authorize_rdp_session(isolated_db, user_id=operator["id"], asset_id=asset["id"])

    assert str(authorization.credential_id) == credential_id


async def test_direct_asset_rule_wins_over_tag_rule(isolated_db, client):
    """Faz 55'in önceliği: aynı asset için hem doğrudan hem etiket
    kuralı varsa DOĞRUDAN kural kazanır (mevcut kullanıcı vs AD grubu
    ilkesiyle AYNI mantık, cihaz hedefine de uygulanır)."""
    from app.pam.service import authorize_ssh_session

    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="priority-op", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.11.17", hostname="priority-target.example.local")
    tag_id = (await client.post("/api/pam/tags", headers=headers, json={"name": "PriorityTag"})).json()["id"]
    await client.put(f"/api/pam/tags/{tag_id}/assets/{asset['id']}", headers=headers)

    tag_credential_id = await _create_credential(client, headers)
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={"user_id": str(operator["id"]), "tag_id": tag_id, "credential_id": tag_credential_id, "allow_ssh": True},
    )
    direct_credential_id = await _create_credential(client, headers)
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "user_id": str(operator["id"]),
            "asset_id": str(asset["id"]),
            "credential_id": direct_credential_id,
            "allow_ssh": True,
        },
    )

    _, _, _, resolved_credential_id = await authorize_ssh_session(isolated_db, user_id=operator["id"], asset_id=asset["id"])

    assert str(resolved_credential_id) == direct_credential_id


async def test_my_access_includes_asset_via_tag_and_group(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="myaccess-op", role="OPERATOR")
    tag_asset = await _seed_asset(isolated_db, ip_address="10.0.11.18", hostname="via-tag.example.local")
    group_asset = await _seed_asset(isolated_db, ip_address="10.0.11.19", hostname="via-group.example.local")
    tag_id = (await client.post("/api/pam/tags", headers=headers, json={"name": "MyAccessTag"})).json()["id"]
    group_id = (await client.post("/api/pam/server-groups", headers=headers, json={"name": "MyAccessGroup"})).json()["id"]
    await client.put(f"/api/pam/tags/{tag_id}/assets/{tag_asset['id']}", headers=headers)
    await client.put(f"/api/pam/server-groups/{group_id}/assets/{group_asset['id']}", headers=headers)
    credential_id = await _create_credential(client, headers)
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={"user_id": str(operator["id"]), "tag_id": tag_id, "credential_id": credential_id, "allow_ssh": True},
    )
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={"user_id": str(operator["id"]), "server_group_id": group_id, "credential_id": credential_id, "allow_rdp": True},
    )

    operator_token = await _login(client, username="myaccess-op")
    response = await client.get("/api/pam/my-access", headers={"Authorization": f"Bearer {operator_token}"})

    hostnames = {row["asset_hostname"] for row in response.json()}
    assert {"via-tag.example.local", "via-group.example.local"} <= hostnames
