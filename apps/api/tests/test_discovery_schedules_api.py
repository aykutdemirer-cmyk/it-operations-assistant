"""Faz 71 — `/api/discovery/schedules` CRUD. `require_role("ADMIN")`
— elle taramanın (`/icmp`) AKSİNE, kalıcı arka plan yapılandırması."""

import pytest

from app.auth.permissions import default_permissions_for_role
from app.auth.security import hash_password
from app.db.users import insert_user, set_permissions

pytestmark = pytest.mark.anyio


async def _headers(client, isolated_db, *, username, role) -> dict:
    row = await insert_user(
        isolated_db, username=username, password_hash=hash_password("s3cret-pw!"), role=role, full_name=None
    )
    await set_permissions(isolated_db, row["id"], default_permissions_for_role(role))
    resp = await client.post("/api/auth/login", json={"username": username, "password": "s3cret-pw!"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_list_empty_by_default(isolated_db, client):
    admin = await _headers(client, isolated_db, username="sched-admin1", role="ADMIN")
    resp = await client.get("/api/discovery/schedules", headers=admin)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_and_list(isolated_db, client):
    admin = await _headers(client, isolated_db, username="sched-admin2", role="ADMIN")
    created = await client.post(
        "/api/discovery/schedules", headers=admin, json={"cidr": "10.20.0.0/24", "interval_hours": 12}
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["cidr"] == "10.20.0.0/24"
    assert body["interval_hours"] == 12
    assert body["enabled"] is True
    assert body["last_run_at"] is None

    listed = (await client.get("/api/discovery/schedules", headers=admin)).json()
    assert len(listed) == 1 and listed[0]["id"] == body["id"]


async def test_create_rejects_invalid_cidr(isolated_db, client):
    admin = await _headers(client, isolated_db, username="sched-admin3", role="ADMIN")
    resp = await client.post(
        "/api/discovery/schedules", headers=admin, json={"cidr": "not-a-cidr", "interval_hours": 24}
    )
    assert resp.status_code == 400


async def test_create_rejects_non_positive_interval(isolated_db, client):
    admin = await _headers(client, isolated_db, username="sched-admin4", role="ADMIN")
    resp = await client.post(
        "/api/discovery/schedules", headers=admin, json={"cidr": "10.0.0.0/24", "interval_hours": 0}
    )
    assert resp.status_code == 422


async def test_update_toggles_enabled_and_interval(isolated_db, client):
    admin = await _headers(client, isolated_db, username="sched-admin5", role="ADMIN")
    created = (
        await client.post("/api/discovery/schedules", headers=admin, json={"cidr": "10.0.0.0/24", "interval_hours": 24})
    ).json()

    updated = await client.put(
        f"/api/discovery/schedules/{created['id']}", headers=admin, json={"enabled": False, "interval_hours": 6}
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["interval_hours"] == 6
    assert updated.json()["cidr"] == "10.0.0.0/24"  # gönderilmeyen alan değişmedi


async def test_update_unknown_returns_404(isolated_db, client):
    admin = await _headers(client, isolated_db, username="sched-admin6", role="ADMIN")
    resp = await client.put(
        "/api/discovery/schedules/00000000-0000-0000-0000-000000000000", headers=admin, json={"enabled": False}
    )
    assert resp.status_code == 404


async def test_delete_removes_schedule(isolated_db, client):
    admin = await _headers(client, isolated_db, username="sched-admin7", role="ADMIN")
    created = (
        await client.post("/api/discovery/schedules", headers=admin, json={"cidr": "10.0.0.0/24", "interval_hours": 24})
    ).json()

    deleted = await client.delete(f"/api/discovery/schedules/{created['id']}", headers=admin)
    assert deleted.status_code == 204
    assert (await client.get("/api/discovery/schedules", headers=admin)).json() == []

    again = await client.delete(f"/api/discovery/schedules/{created['id']}", headers=admin)
    assert again.status_code == 404


async def test_non_admin_forbidden(isolated_db, client):
    op = await _headers(client, isolated_db, username="sched-op", role="OPERATOR")
    assert (await client.get("/api/discovery/schedules", headers=op)).status_code == 403
    assert (
        await client.post("/api/discovery/schedules", headers=op, json={"cidr": "10.0.0.0/24", "interval_hours": 24})
    ).status_code == 403
