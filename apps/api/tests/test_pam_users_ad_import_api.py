"""Faz 52 — `POST /api/pam/users/from-ad` için gerçek PostgreSQL'e bağlı
testler (bkz. kök `conftest.py::isolated_db`)."""

import pytest

from app.auth.permissions import default_permissions_for_role
from app.auth.security import hash_password
from app.db.users import insert_user, set_permissions

pytestmark = pytest.mark.anyio


async def _seed_user(isolated_db, *, username, role, password="s3cret-pw!"):
    row = await insert_user(isolated_db, username=username, password_hash=hash_password(password), role=role, full_name=None)
    await set_permissions(isolated_db, row["id"], default_permissions_for_role(role))
    return row


async def _login(client, *, username, password="s3cret-pw!") -> str:
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _admin_headers(isolated_db, client, username="import-admin") -> dict:
    await _seed_user(isolated_db, username=username, role="ADMIN")
    token = await _login(client, username=username)
    return {"Authorization": f"Bearer {token}"}


async def _seed_ad_user(isolated_db, *, username, display_name="Test User"):
    await isolated_db.execute(
        "INSERT INTO ad_users (distinguished_name, username, display_name) VALUES ($1, $2, $3)",
        f"CN={display_name},DC=lab,DC=local",
        username,
        display_name,
    )


async def test_import_from_ad_requires_pam_admin(isolated_db, client):
    await _seed_user(isolated_db, username="viewer-import", role="VIEWER")
    token = await _login(client, username="viewer-import")

    response = await client.post(
        "/api/pam/users/from-ad", headers={"Authorization": f"Bearer {token}"}, json={"ad_username": "x", "role": "VIEWER"}
    )

    assert response.status_code == 403


async def test_import_from_ad_returns_404_when_not_synced(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)

    response = await client.post("/api/pam/users/from-ad", headers=headers, json={"ad_username": "ghost", "role": "VIEWER"})

    assert response.status_code == 404


async def test_import_from_ad_creates_user_with_chosen_role(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await _seed_ad_user(isolated_db, username="asmith", display_name="Alice Smith")

    response = await client.post("/api/pam/users/from-ad", headers=headers, json={"ad_username": "asmith", "role": "OPERATOR"})

    assert response.status_code == 201
    body = response.json()
    assert body["ad_username"] == "asmith"
    assert body["role"] == "OPERATOR"
    assert body["full_name"] == "Alice Smith"


async def test_import_from_ad_rejects_double_import(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await _seed_ad_user(isolated_db, username="bwayne")
    first = await client.post("/api/pam/users/from-ad", headers=headers, json={"ad_username": "bwayne", "role": "VIEWER"})
    assert first.status_code == 201

    second = await client.post("/api/pam/users/from-ad", headers=headers, json={"ad_username": "bwayne", "role": "VIEWER"})

    assert second.status_code == 409


async def test_imported_ad_user_appears_in_users_list_with_ad_username(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await _seed_ad_user(isolated_db, username="ckent")
    await client.post("/api/pam/users/from-ad", headers=headers, json={"ad_username": "ckent", "role": "VIEWER"})

    response = await client.get("/api/pam/users", headers=headers)

    assert response.status_code == 200
    matching = [u for u in response.json() if u["username"] == "ckent"]
    assert len(matching) == 1
    assert matching[0]["ad_username"] == "ckent"
