"""Faz 46/47 — `/api/auth/*` için gerçek PostgreSQL'e bağlı testler.
`isolated_db` sayesinde gerçek/kalıcı veriye etkisi yok (bkz. kök
`conftest.py`)."""

from unittest.mock import patch

import pytest

from app.auth.permissions import default_permissions_for_role
from app.auth.security import hash_password
from app.db.ldap import upsert_config
from app.db.users import insert_user, set_permissions


async def _seed_user(isolated_db, *, username="alice", password="s3cret-pw!", role="VIEWER", is_active=True):
    row = await insert_user(
        isolated_db, username=username, password_hash=hash_password(password), role=role, full_name=None
    )
    # `insert_user` (db katmanı) izin ATAMAZ — gerçek akışta bunu
    # `app/auth/service.py::create_user` yapar; doğrudan db fonksiyonunu
    # çağıran bu testler rolün VARSAYILAN iznini kendisi kuruyor (bkz.
    # `app/auth/permissions.py`).
    await set_permissions(isolated_db, row["id"], default_permissions_for_role(role))
    if not is_active:
        await isolated_db.execute("UPDATE users SET is_active = false WHERE id = $1", row["id"])
    return row


@pytest.mark.anyio
async def test_login_success_returns_token(isolated_db, client):
    await _seed_user(isolated_db, username="alice", password="s3cret-pw!", role="OPERATOR")

    response = await client.post("/api/auth/login", json={"username": "alice", "password": "s3cret-pw!"})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "alice"
    assert body["user"]["role"] == "OPERATOR"
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]


@pytest.mark.anyio
async def test_login_wrong_password_returns_401(isolated_db, client):
    await _seed_user(isolated_db, username="alice", password="s3cret-pw!")

    response = await client.post("/api/auth/login", json={"username": "alice", "password": "yanlis"})

    assert response.status_code == 401


@pytest.mark.anyio
async def test_login_unknown_username_returns_401_same_as_wrong_password(isolated_db, client):
    response = await client.post("/api/auth/login", json={"username": "no-such-user", "password": "x"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Kullanıcı adı veya parola hatalı"


# ---- Faz 52 — LDAP Bind-Auth Girişi (opt-in) --------------------------


async def _seed_ldap_config(isolated_db):
    await upsert_config(
        isolated_db,
        host="dc01.lab.local",
        port=636,
        use_ssl=True,
        domain_fqdn="lab.local",
        base_dn="DC=lab,DC=local",
        bind_dn="svc_ldap@lab.local",
        encrypted_bind_password="unused-in-these-tests",
    )


async def _seed_ad_user(isolated_db, *, username, display_name="Test User"):
    await isolated_db.execute(
        "INSERT INTO ad_users (distinguished_name, username, display_name) VALUES ($1, $2, $3)",
        f"CN={display_name},DC=lab,DC=local",
        username,
        display_name,
    )


@pytest.mark.anyio
async def test_login_does_not_fall_back_to_ldap_when_disabled(isolated_db, client, monkeypatch):
    monkeypatch.delenv("LDAP_AUTH_ENABLED", raising=False)
    await _seed_ldap_config(isolated_db)
    await _seed_ad_user(isolated_db, username="jdoe")

    with patch("app.services.ldap_auth._run_bind", return_value=True):
        response = await client.post("/api/auth/login", json={"username": "jdoe", "password": "x"})

    assert response.status_code == 401


@pytest.mark.anyio
async def test_login_via_ldap_auto_provisions_and_returns_token(isolated_db, client, monkeypatch):
    monkeypatch.setenv("LDAP_AUTH_ENABLED", "true")
    monkeypatch.setenv("LDAP_AUTH_DEFAULT_ROLE", "VIEWER")
    await _seed_ldap_config(isolated_db)
    await _seed_ad_user(isolated_db, username="jdoe", display_name="John Doe")

    with patch("app.services.ldap_auth._run_bind", return_value=True):
        response = await client.post("/api/auth/login", json={"username": "jdoe", "password": "correct"})

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["username"] == "jdoe"
    assert body["user"]["ad_username"] == "jdoe"
    assert body["user"]["role"] == "VIEWER"


@pytest.mark.anyio
async def test_login_local_user_takes_priority_over_ldap(isolated_db, client, monkeypatch):
    """Yerel şifre DOĞRU eşleşiyorsa LDAP'a hiç bakılmaz — `_run_bind`
    hiç ÇAĞRILMAZ (mock'lanmadığı için çağrılırsa gerçek bir ağ
    isteği denenip test zaman aşımına uğrardı)."""
    monkeypatch.setenv("LDAP_AUTH_ENABLED", "true")
    await _seed_user(isolated_db, username="alice", password="s3cret-pw!", role="ADMIN")

    response = await client.post("/api/auth/login", json={"username": "alice", "password": "s3cret-pw!"})

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "ADMIN"


@pytest.mark.anyio
async def test_login_inactive_user_returns_401(isolated_db, client):
    await _seed_user(isolated_db, username="bob", password="s3cret-pw!", is_active=False)

    response = await client.post("/api/auth/login", json={"username": "bob", "password": "s3cret-pw!"})

    assert response.status_code == 401


@pytest.mark.anyio
async def test_me_requires_bearer_token(client):
    response = await client.get("/api/auth/me")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_me_returns_current_user_with_valid_token(isolated_db, client):
    await _seed_user(isolated_db, username="carol", password="s3cret-pw!", role="ADMIN")
    login_response = await client.post("/api/auth/login", json={"username": "carol", "password": "s3cret-pw!"})
    token = login_response.json()["access_token"]

    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["username"] == "carol"


@pytest.mark.anyio
async def test_me_rejects_garbage_token(client):
    response = await client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401


@pytest.mark.anyio
async def test_pam_users_route_requires_admin_role(isolated_db, client):
    """OPERATOR bir ADMIN-only PAM endpoint'ine erişemez (403) —
    kimlik doğrulandı ama yetki yetersiz."""
    await _seed_user(isolated_db, username="dave", password="s3cret-pw!", role="OPERATOR")
    login_response = await client.post("/api/auth/login", json={"username": "dave", "password": "s3cret-pw!"})
    token = login_response.json()["access_token"]

    response = await client.get("/api/pam/users", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


@pytest.mark.anyio
async def test_pam_users_route_allows_admin_role(isolated_db, client):
    await _seed_user(isolated_db, username="eve", password="s3cret-pw!", role="ADMIN")
    login_response = await client.post("/api/auth/login", json={"username": "eve", "password": "s3cret-pw!"})
    token = login_response.json()["access_token"]

    response = await client.get("/api/pam/users", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    usernames = [u["username"] for u in response.json()]
    assert "eve" in usernames
