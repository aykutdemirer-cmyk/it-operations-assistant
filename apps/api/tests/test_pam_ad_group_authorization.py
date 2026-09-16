"""Faz 49 — AD grup üyeliğinden gelen PAM erişim kurallarının uçtan uca
davranışı: bir yerel kullanıcı `users.ad_username` ile bir AD hesabına
bağlanır, o hesabın (senkronize edilmiş) grup üyeliklerinden gelen
`pam_access_rules` kuralları `GET /api/pam/my-access` ve `authorize_
{ssh,rdp}_session`'da dikkate alınır. Gerçek bir AD sunucusu
kullanılmaz — `app.services.ldap._blocking_search` mock'lanır."""

from datetime import datetime, timezone
from unittest.mock import patch

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


async def _admin_headers(isolated_db, client, username="admin-adgroup") -> dict:
    await _seed_user(isolated_db, username=username, role="ADMIN")
    token = await _login(client, username=username)
    return {"Authorization": f"Bearer {token}"}


async def _seed_asset(isolated_db, **overrides) -> dict:
    defaults = dict(
        ip_address="10.0.9.40",
        hostname="ad-target.example.local",
        mac_address="AA-BB-CC-DD-EE-40",
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


async def _sync_one_ad_user_in_one_group(client, headers, *, ad_username: str, group_name: str) -> str:
    config_payload = {
        "host": "dc01.lab.local",
        "port": 389,
        "use_ssl": False,
        "domain_fqdn": "lab.local",
        "base_dn": "DC=lab,DC=local",
        "bind_dn": "svc-ldap-sync@lab.local",
        "bind_password": "s3cret",
    }
    await client.put("/api/settings/ldap", headers=headers, json=config_payload)

    group_dn = f"CN={group_name},OU=Groups,DC=lab,DC=local"
    groups = [{"dn": group_dn, "name": group_name}]
    users = [
        {
            "dn": f"CN={ad_username},OU=Users,DC=lab,DC=local",
            "username": ad_username,
            "display_name": ad_username,
            "member_of": [group_dn],
        }
    ]
    with patch("app.services.ldap._blocking_search", return_value=(groups, users)):
        sync_response = await client.post("/api/settings/ldap/sync", headers=headers)
    assert sync_response.status_code == 200
    return group_dn


async def test_link_user_to_unknown_ad_username_returns_422(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator-unlinked", role="OPERATOR")

    response = await client.put(
        f"/api/pam/users/{operator['id']}", headers=headers, json={"ad_username": "does-not-exist"}
    )

    assert response.status_code == 422


async def test_my_access_includes_asset_authorized_via_ad_group_membership(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator-adgroup1", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.41")
    await _sync_one_ad_user_in_one_group(client, headers, ad_username="jdoe", group_name="IT-Helpdesk")

    link_response = await client.put(f"/api/pam/users/{operator['id']}", headers=headers, json={"ad_username": "jdoe"})
    assert link_response.status_code == 200, link_response.text

    groups_response = await client.get("/api/settings/ldap/groups", headers=headers)
    group_id = groups_response.json()[0]["id"]

    credential_response = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "ad-target-root", "credential_type": "password", "username": "root", "password": "hunter2"},
    )
    rule_response = await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "ad_group_id": group_id,
            "asset_id": str(asset["id"]),
            "credential_id": credential_response.json()["id"],
            "allow_ssh": True,
        },
    )
    assert rule_response.status_code == 201, rule_response.text

    operator_token = await _login(client, username="operator-adgroup1")
    my_access = await client.get("/api/pam/my-access", headers={"Authorization": f"Bearer {operator_token}"})

    assert my_access.status_code == 200
    hostnames = [row["asset_hostname"] for row in my_access.json()]
    assert hostnames == ["ad-target.example.local"]


async def test_direct_rule_wins_over_ad_group_rule_for_same_asset(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator-adgroup2", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.42")
    await _sync_one_ad_user_in_one_group(client, headers, ad_username="asmith", group_name="SOC-Team")
    await client.put(f"/api/pam/users/{operator['id']}", headers=headers, json={"ad_username": "asmith"})
    group_id = (await client.get("/api/settings/ldap/groups", headers=headers)).json()[0]["id"]

    group_credential = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "group-cred", "credential_type": "password", "username": "group-user", "password": "x"},
    )
    direct_credential = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "direct-cred", "credential_type": "password", "username": "direct-user", "password": "y"},
    )
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "ad_group_id": group_id,
            "asset_id": str(asset["id"]),
            "credential_id": group_credential.json()["id"],
            "allow_ssh": True,
            "max_session_duration_mins": 15,
        },
    )
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "user_id": str(operator["id"]),
            "asset_id": str(asset["id"]),
            "credential_id": direct_credential.json()["id"],
            "allow_ssh": True,
            "max_session_duration_mins": 90,
        },
    )

    from app.pam.service import authorize_ssh_session

    username, _payload, max_duration, _credential_id = await authorize_ssh_session(
        isolated_db, user_id=operator["id"], asset_id=asset["id"]
    )

    assert username == "direct-user"
    assert max_duration == 90


async def test_authorize_ssh_session_grants_access_via_ad_group_rule_only(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator-adgroup3", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.43")
    await _sync_one_ad_user_in_one_group(client, headers, ad_username="bwayne", group_name="Domain Admins")
    await client.put(f"/api/pam/users/{operator['id']}", headers=headers, json={"ad_username": "bwayne"})
    group_id = (await client.get("/api/settings/ldap/groups", headers=headers)).json()[0]["id"]

    credential = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "domain-admin-cred", "credential_type": "password", "username": "admin", "password": "z"},
    )
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "ad_group_id": group_id,
            "asset_id": str(asset["id"]),
            "credential_id": credential.json()["id"],
            "allow_ssh": True,
        },
    )

    from app.pam.service import authorize_ssh_session

    username, _payload, _max_duration, _credential_id = await authorize_ssh_session(
        isolated_db, user_id=operator["id"], asset_id=asset["id"]
    )

    assert username == "admin"


async def test_unlinked_user_gets_no_access_from_ad_group_rules(isolated_db, client):
    from app.pam.service import SshNotAuthorizedError, authorize_ssh_session

    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator-unlinked2", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.44")
    await _sync_one_ad_user_in_one_group(client, headers, ad_username="nolink", group_name="SOC-Team-2")
    group_id = (await client.get("/api/settings/ldap/groups", headers=headers)).json()[0]["id"]
    credential = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "unlinked-cred", "credential_type": "password", "username": "root", "password": "z"},
    )
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "ad_group_id": group_id,
            "asset_id": str(asset["id"]),
            "credential_id": credential.json()["id"],
            "allow_ssh": True,
        },
    )

    with pytest.raises(SshNotAuthorizedError):
        await authorize_ssh_session(isolated_db, user_id=operator["id"], asset_id=asset["id"])


async def test_create_rule_rejects_both_user_id_and_ad_group_id(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator-bothtarget", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.45")
    await _sync_one_ad_user_in_one_group(client, headers, ad_username="bothtarget", group_name="Both-Target-Group")
    group_id = (await client.get("/api/settings/ldap/groups", headers=headers)).json()[0]["id"]
    credential = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "both-cred", "credential_type": "password", "username": "root", "password": "z"},
    )

    response = await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "user_id": str(operator["id"]),
            "ad_group_id": group_id,
            "asset_id": str(asset["id"]),
            "credential_id": credential.json()["id"],
            "allow_ssh": True,
        },
    )

    assert response.status_code == 422
