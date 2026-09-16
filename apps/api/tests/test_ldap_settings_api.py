"""Faz 49 — `/api/settings/ldap/*` için gerçek PostgreSQL'e bağlı
testler (bkz. kök `conftest.py::isolated_db`). Gerçek bir AD sunucusuna
hiçbir testte bağlanılmaz — `app.services.ldap._blocking_search`
mock'lanır (bkz. `tests/services/test_ldap_service.py`)."""

from unittest.mock import patch

import pytest
from ldap3.core.exceptions import LDAPBindError

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


async def _admin_headers(isolated_db, client, username="ldap-admin") -> dict:
    await _seed_user(isolated_db, username=username, role="ADMIN")
    token = await _login(client, username=username)
    return {"Authorization": f"Bearer {token}"}


async def _clear_saved_config(isolated_db) -> None:
    """`ldap_config` tek-satırlı (id=1) bir tablo — kullanıcı GERÇEKTEN
    Ayarlar ekranından bir LDAP yapılandırması kaydettiği için canlı
    veritabanında artık GERÇEK bir satır var. `isolated_db`'nin
    transaction-rollback izolasyonu bu satırı GÖRÜR (zaten commit
    edilmiş) — "hiç yapılandırma yok" varsayan testler bu satırı
    kendi (test sonunda rollback edilen, gerçek veriye KALICI etkisi
    olmayan) transaction'ları içinde silmeli."""
    await isolated_db.execute("DELETE FROM ldap_config")


def _config_payload(**overrides) -> dict:
    payload = {
        "host": "dc01.lab.local",
        "port": 389,
        "use_ssl": False,
        "domain_fqdn": "lab.local",
        "base_dn": "DC=lab,DC=local",
        "bind_dn": "svc-ldap-sync@lab.local",
        "bind_password": "s3cret",
    }
    payload.update(overrides)
    return payload


async def test_put_ldap_config_without_password_on_first_save_returns_422(isolated_db, client):
    """İlk kayıtta parola zorunlu — henüz KAYITLI bir yapılandırma
    olmadan "değiştirme" anlamına gelen `None` gönderilirse (frontend'in
    boş bırakılan parola alanı için yaptığı gibi) fallback edecek bir
    değer yoktur."""
    headers = await _admin_headers(isolated_db, client)
    await _clear_saved_config(isolated_db)

    response = await client.put("/api/settings/ldap", headers=headers, json=_config_payload(bind_password=None))

    assert response.status_code == 422


async def test_put_ldap_config_with_empty_password_keeps_existing_encrypted_password(isolated_db, client):
    """Vault kimlik bilgisi güncellemesiyle AYNI ilke: `bind_password`
    boş/`None` gönderilirse (host/port gibi başka alanları değiştirirken
    parolayı yeniden yazmak istemeyen admin) mevcut şifreli parola
    KORUNUR — üzerine yazılmaz."""
    headers = await _admin_headers(isolated_db, client)
    await client.put("/api/settings/ldap", headers=headers, json=_config_payload(bind_password="ilk-parola"))
    before = await isolated_db.fetchval("SELECT encrypted_bind_password FROM ldap_config WHERE id = 1")

    response = await client.put(
        "/api/settings/ldap", headers=headers, json=_config_payload(port=636, bind_password=None)
    )

    assert response.status_code == 200
    assert response.json()["port"] == 636
    after = await isolated_db.fetchval("SELECT encrypted_bind_password FROM ldap_config WHERE id = 1")
    assert after == before


async def test_test_connection_without_password_uses_saved_password(isolated_db, client):
    """"Bağlantıyı Test Et" boş parolayla çağrılırsa (host/port'u
    deneyip parolayı yeniden yazmak istemeyen admin) KAYITLI parolayla
    test eder."""
    headers = await _admin_headers(isolated_db, client)
    await client.put("/api/settings/ldap", headers=headers, json=_config_payload(bind_password="kayitli-parola"))

    captured_passwords = []

    def _fake_test_connection(params):
        captured_passwords.append(params["bind_password"])

    with patch("app.routes.ldap_settings.test_connection", side_effect=_fake_test_connection):
        response = await client.post(
            "/api/settings/ldap/test", headers=headers, json=_config_payload(port=636, bind_password=None)
        )

    assert response.status_code == 200
    assert captured_passwords == ["kayitli-parola"]


async def test_test_connection_without_password_and_no_saved_config_returns_422(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await _clear_saved_config(isolated_db)

    response = await client.post("/api/settings/ldap/test", headers=headers, json=_config_payload(bind_password=None))

    assert response.status_code == 422


async def test_get_ldap_config_returns_null_when_unconfigured(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await _clear_saved_config(isolated_db)

    response = await client.get("/api/settings/ldap", headers=headers)

    assert response.status_code == 200
    assert response.json() is None


async def test_ldap_routes_require_pam_admin(isolated_db, client):
    await _seed_user(isolated_db, username="viewer-ldap", role="VIEWER")
    token = await _login(client, username="viewer-ldap")

    response = await client.get("/api/settings/ldap", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


async def test_put_ldap_config_masks_bind_password_in_response(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)

    response = await client.put("/api/settings/ldap", headers=headers, json=_config_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["bind_password_masked"] == "••••••••"
    assert "s3cret" not in response.text


async def test_put_ldap_config_persists_encrypted_password_not_plaintext(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)

    await client.put("/api/settings/ldap", headers=headers, json=_config_payload())

    row = await isolated_db.fetchrow("SELECT encrypted_bind_password FROM ldap_config WHERE id = 1")
    assert "s3cret" not in row["encrypted_bind_password"]


async def test_test_connection_returns_success_true_without_persisting_config(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await _clear_saved_config(isolated_db)

    with patch("app.routes.ldap_settings.test_connection", return_value=None):
        response = await client.post("/api/settings/ldap/test", headers=headers, json=_config_payload())

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Bağlantı başarılı"}
    assert await isolated_db.fetchval("SELECT count(*) FROM ldap_config") == 0


async def test_test_connection_returns_success_false_on_bind_failure(isolated_db, client):
    from app.services.ldap import LdapConnectError

    headers = await _admin_headers(isolated_db, client)

    with patch("app.routes.ldap_settings.test_connection", side_effect=LdapConnectError("bağlanılamadı")):
        response = await client.post("/api/settings/ldap/test", headers=headers, json=_config_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False


async def test_sync_without_saved_config_returns_409(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await _clear_saved_config(isolated_db)

    response = await client.post("/api/settings/ldap/sync", headers=headers)

    assert response.status_code == 409


async def test_sync_persists_groups_and_updates_last_sync_status(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await client.put("/api/settings/ldap", headers=headers, json=_config_payload())

    groups = [{"dn": "CN=IT-Helpdesk,DC=lab,DC=local", "name": "IT-Helpdesk"}]
    with patch("app.services.ldap._blocking_search", return_value=(groups, [])):
        response = await client.post("/api/settings/ldap/sync", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"groups_synced": 1, "users_synced": 0, "memberships_synced": 0}

    config = await client.get("/api/settings/ldap", headers=headers)
    assert config.json()["last_sync_status"] == "success"


async def test_sync_failure_records_error_status_and_returns_502(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await client.put("/api/settings/ldap", headers=headers, json=_config_payload())

    with patch("app.services.ldap._blocking_search", side_effect=LDAPBindError("invalid credentials")):
        response = await client.post("/api/settings/ldap/sync", headers=headers)

    assert response.status_code == 502
    config = await client.get("/api/settings/ldap", headers=headers)
    assert config.json()["last_sync_status"] == "error"


async def test_list_ad_groups_returns_synced_groups(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    await client.put("/api/settings/ldap", headers=headers, json=_config_payload())
    groups = [{"dn": "CN=SOC-Team,DC=lab,DC=local", "name": "SOC-Team"}]
    with patch("app.services.ldap._blocking_search", return_value=(groups, [])):
        await client.post("/api/settings/ldap/sync", headers=headers)

    response = await client.get("/api/settings/ldap/groups", headers=headers)

    assert response.status_code == 200
    names = [row["name"] for row in response.json()]
    assert names == ["SOC-Team"]


async def test_list_ad_users_returns_synced_users(isolated_db, client):
    """Faz 52 — `/pam/users`'ın "Active Directory'den İçe Aktar"
    seçicisinin veri kaynağı."""
    headers = await _admin_headers(isolated_db, client)
    await client.put("/api/settings/ldap", headers=headers, json=_config_payload())
    users = [
        {"dn": "CN=Jane Doe,DC=lab,DC=local", "username": "jdoe", "display_name": "Jane Doe", "email": "jdoe@lab.local", "member_of": []}
    ]
    with patch("app.services.ldap._blocking_search", return_value=([], users)):
        await client.post("/api/settings/ldap/sync", headers=headers)

    response = await client.get("/api/settings/ldap/users", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["username"] == "jdoe"
    assert body[0]["display_name"] == "Jane Doe"
    assert body[0]["email"] == "jdoe@lab.local"
