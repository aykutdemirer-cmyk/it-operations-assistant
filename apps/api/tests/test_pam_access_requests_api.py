"""Faz 56 — `/api/pam/access-requests` (talep aç/listele/onayla/reddet)
için gerçek PostgreSQL'e bağlı testler. Onaylamanın GERÇEKTEN mevcut
`pam_access_rules` motorunu (Faz 46-55) kullandığı — yeni bir paralel
yetkilendirme mekanizması OLMADIĞI — `authorize_ssh_session`/
`authorize_rdp_session`'a karşı doğrudan doğrulanır."""

from datetime import datetime, timedelta, timezone

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


async def _admin_headers(isolated_db, client, username="req-admin") -> dict:
    await _seed_user(isolated_db, username=username, role="ADMIN")
    token = await _login(client, username=username)
    return {"Authorization": f"Bearer {token}"}


async def _seed_asset(isolated_db, **overrides) -> dict:
    defaults = dict(
        ip_address="10.0.12.10",
        hostname="req-target.example.local",
        mac_address="AA-BB-CC-DD-EE-70",
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


async def test_create_request_requires_exactly_one_device_target(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="req-op1", role="OPERATOR")
    op_token = await _login(client, username="req-op1")
    op_headers = {"Authorization": f"Bearer {op_token}"}
    asset = await _seed_asset(isolated_db, ip_address="10.0.12.11")

    response = await client.post(
        "/api/pam/access-requests",
        headers=op_headers,
        json={"protocol": "ssh", "business_reason": "acil bakım"},
    )
    assert response.status_code == 422

    response2 = await client.post(
        "/api/pam/access-requests",
        headers=op_headers,
        json={"asset_id": str(asset["id"]), "protocol": "ssh", "business_reason": "acil bakım"},
    )
    assert response2.status_code == 201
    assert response2.json()["status"] == "pending"
    assert response2.json()["requester_username"] == "req-op1"


async def test_user_can_only_list_own_requests(isolated_db, client):
    await _admin_headers(isolated_db, client)
    op1 = await _seed_user(isolated_db, username="req-mine1", role="OPERATOR")
    op2 = await _seed_user(isolated_db, username="req-mine2", role="OPERATOR")
    op1_token = await _login(client, username="req-mine1")
    op2_token = await _login(client, username="req-mine2")
    asset = await _seed_asset(isolated_db, ip_address="10.0.12.12")

    await client.post(
        "/api/pam/access-requests",
        headers={"Authorization": f"Bearer {op1_token}"},
        json={"asset_id": str(asset["id"]), "protocol": "ssh", "business_reason": "x"},
    )
    await client.post(
        "/api/pam/access-requests",
        headers={"Authorization": f"Bearer {op2_token}"},
        json={"asset_id": str(asset["id"]), "protocol": "rdp", "business_reason": "y"},
    )

    response = await client.get("/api/pam/access-requests/mine", headers={"Authorization": f"Bearer {op1_token}"})

    assert response.status_code == 200
    usernames = {row["requester_username"] for row in response.json()}
    assert usernames == {"req-mine1"}


async def test_non_admin_cannot_list_all_requests(isolated_db, client):
    await _seed_user(isolated_db, username="req-nonadmin", role="OPERATOR")
    token = await _login(client, username="req-nonadmin")

    response = await client.get("/api/pam/access-requests", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


async def test_approve_creates_new_rule_and_grants_real_access(isolated_db, client):
    from app.pam.service import authorize_ssh_session

    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="req-approve1", role="OPERATOR")
    op_token = await _login(client, username="req-approve1")
    asset = await _seed_asset(isolated_db, ip_address="10.0.12.13", hostname="approve-target.example.local")
    credential_id = await _create_credential(client, headers)

    create_response = await client.post(
        "/api/pam/access-requests",
        headers={"Authorization": f"Bearer {op_token}"},
        json={"asset_id": str(asset["id"]), "protocol": "ssh", "business_reason": "bakım", "requested_duration_mins": 30},
    )
    request_id = create_response.json()["id"]

    approve_response = await client.post(
        f"/api/pam/access-requests/{request_id}/approve", headers=headers, json={"credential_id": credential_id}
    )

    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    username, payload, max_duration, cred_id = await authorize_ssh_session(
        isolated_db, user_id=operator["id"], asset_id=asset["id"]
    )
    assert username == "root"
    assert str(cred_id) == credential_id
    assert max_duration == 30


async def test_approve_extends_existing_rule_instead_of_duplicating(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="req-extend1", role="OPERATOR")
    op_token = await _login(client, username="req-extend1")
    asset = await _seed_asset(isolated_db, ip_address="10.0.12.14")
    credential_id = await _create_credential(client, headers)

    # Zaten SSH izni veren bir kural var (Admin'in elle oluşturduğu).
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "user_id": str(operator["id"]),
            "asset_id": str(asset["id"]),
            "credential_id": credential_id,
            "allow_ssh": True,
        },
    )

    create_response = await client.post(
        "/api/pam/access-requests",
        headers={"Authorization": f"Bearer {op_token}"},
        json={"asset_id": str(asset["id"]), "protocol": "rdp", "business_reason": "x"},
    )
    request_id = create_response.json()["id"]

    await client.post(f"/api/pam/access-requests/{request_id}/approve", headers=headers, json={"credential_id": credential_id})

    rules_response = await client.get("/api/pam/rules", headers=headers, params={"search": "req-extend1"})
    matching = [r for r in rules_response.json() if r["asset_id"] == str(asset["id"])]
    assert len(matching) == 1  # yeni bir satır AÇILMADI, mevcut olan GENİŞLETİLDİ
    assert matching[0]["allow_ssh"] is True
    assert matching[0]["allow_rdp"] is True


async def test_reject_marks_status_and_creates_no_rule(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="req-reject1", role="OPERATOR")
    op_token = await _login(client, username="req-reject1")
    asset = await _seed_asset(isolated_db, ip_address="10.0.12.15")

    create_response = await client.post(
        "/api/pam/access-requests",
        headers={"Authorization": f"Bearer {op_token}"},
        json={"asset_id": str(asset["id"]), "protocol": "ssh", "business_reason": "x"},
    )
    request_id = create_response.json()["id"]

    reject_response = await client.post(
        f"/api/pam/access-requests/{request_id}/reject", headers=headers, json={"review_note": "yetersiz gerekçe"}
    )

    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"
    assert reject_response.json()["review_note"] == "yetersiz gerekçe"

    from app.pam.service import SshNotAuthorizedError, authorize_ssh_session

    with pytest.raises(SshNotAuthorizedError):
        await authorize_ssh_session(isolated_db, user_id=operator["id"], asset_id=asset["id"])


async def test_cannot_approve_already_reviewed_request(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await _seed_user(isolated_db, username="req-double1", role="OPERATOR")
    op_token = await _login(client, username="req-double1")
    asset = await _seed_asset(isolated_db, ip_address="10.0.12.16")
    credential_id = await _create_credential(client, headers)

    create_response = await client.post(
        "/api/pam/access-requests",
        headers={"Authorization": f"Bearer {op_token}"},
        json={"asset_id": str(asset["id"]), "protocol": "ssh", "business_reason": "x"},
    )
    request_id = create_response.json()["id"]
    await client.post(f"/api/pam/access-requests/{request_id}/reject", headers=headers, json={})

    response = await client.post(
        f"/api/pam/access-requests/{request_id}/approve", headers=headers, json={"credential_id": credential_id}
    )

    assert response.status_code == 409


async def test_approve_via_tag_target_grants_access_for_tagged_asset(isolated_db, client):
    from app.pam.service import authorize_rdp_session

    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="req-tag1", role="OPERATOR")
    op_token = await _login(client, username="req-tag1")
    asset = await _seed_asset(isolated_db, ip_address="10.0.12.17", hostname="tag-req-target.example.local")
    tag_response = await client.post("/api/pam/tags", headers=headers, json={"name": "ReqTag"})
    tag_id = tag_response.json()["id"]
    await client.put(f"/api/pam/tags/{tag_id}/assets/{asset['id']}", headers=headers)
    credential_id = await _create_credential(client, headers)

    create_response = await client.post(
        "/api/pam/access-requests",
        headers={"Authorization": f"Bearer {op_token}"},
        json={"tag_id": tag_id, "protocol": "rdp", "business_reason": "x"},
    )
    request_id = create_response.json()["id"]
    await client.post(f"/api/pam/access-requests/{request_id}/approve", headers=headers, json={"credential_id": credential_id})

    authorization = await authorize_rdp_session(isolated_db, user_id=operator["id"], asset_id=asset["id"])
    assert str(authorization.credential_id) == credential_id
