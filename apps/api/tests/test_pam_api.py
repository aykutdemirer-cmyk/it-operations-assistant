"""Faz 46/47 — `/api/pam/*` için gerçek PostgreSQL'e bağlı testler.
`isolated_db` sayesinde gerçek/kalıcı veriye etkisi yok (bkz. kök
`conftest.py`). Gerçek bir SSH/ağ bağlantısı hiçbir testte açılmaz."""

from datetime import datetime, timedelta, timezone

import pytest

from app.auth.permissions import default_permissions_for_role
from app.auth.security import hash_password
from app.db.assets import upsert_asset
from app.db.users import insert_user, set_permissions


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


async def _seed_asset(isolated_db, **overrides) -> dict:
    defaults = dict(
        ip_address="10.0.9.20",
        hostname="server.example.local",
        mac_address="AA-BB-CC-DD-EE-02",
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


async def _admin_headers(isolated_db, client) -> dict:
    await _seed_user(isolated_db, username="admin1", role="ADMIN")
    token = await _login(client, username="admin1")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_create_vault_credential_masks_secret_in_response(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)

    response = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "srv1-root", "credential_type": "password", "username": "root", "password": "hunter2"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["secret_masked"] == "••••••••"
    assert "hunter2" not in response.text
    assert "password" not in body


@pytest.mark.anyio
async def test_reveal_vault_credential_returns_real_secret_admin_only(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    create_response = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "srv2-root", "credential_type": "password", "username": "root", "password": "hunter2"},
    )
    credential_id = create_response.json()["id"]

    reveal_response = await client.post(f"/api/pam/vault/{credential_id}/reveal", headers=headers)

    assert reveal_response.status_code == 200
    assert reveal_response.json()["password"] == "hunter2"


@pytest.mark.anyio
async def test_reveal_vault_credential_requires_admin(isolated_db, client):
    await _seed_user(isolated_db, username="viewer1", role="VIEWER")
    admin_headers = await _admin_headers(isolated_db, client)
    create_response = await client.post(
        "/api/pam/vault",
        headers=admin_headers,
        json={"name": "srv3-root", "credential_type": "password", "username": "root", "password": "hunter2"},
    )
    credential_id = create_response.json()["id"]
    viewer_token = await _login(client, username="viewer1")

    response = await client.post(
        f"/api/pam/vault/{credential_id}/reveal", headers={"Authorization": f"Bearer {viewer_token}"}
    )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_delete_credential_in_use_returns_409(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator1", role="OPERATOR")
    asset = await _seed_asset(isolated_db)
    credential_response = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "srv4-root", "credential_type": "password", "username": "root", "password": "hunter2"},
    )
    credential_id = credential_response.json()["id"]
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

    response = await client.delete(f"/api/pam/vault/{credential_id}", headers=headers)

    assert response.status_code == 409


@pytest.mark.anyio
async def test_create_rule_duplicate_user_asset_returns_409(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator2", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.21")
    credential_response = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "srv5-root", "credential_type": "password", "username": "root", "password": "hunter2"},
    )
    credential_id = credential_response.json()["id"]
    rule_payload = {
        "user_id": str(operator["id"]),
        "asset_id": str(asset["id"]),
        "credential_id": credential_id,
        "allow_ssh": True,
    }

    first = await client.post("/api/pam/rules", headers=headers, json=rule_payload)
    second = await client.post("/api/pam/rules", headers=headers, json=rule_payload)

    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.anyio
async def test_my_access_lists_only_own_non_expired_rules(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator3", role="OPERATOR")
    active_asset = await _seed_asset(isolated_db, ip_address="10.0.9.22", hostname="active.example.local")
    expired_asset = await _seed_asset(isolated_db, ip_address="10.0.9.23", hostname="expired.example.local")
    credential_response = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "srv6-root", "credential_type": "password", "username": "root", "password": "hunter2"},
    )
    credential_id = credential_response.json()["id"]

    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "user_id": str(operator["id"]),
            "asset_id": str(active_asset["id"]),
            "credential_id": credential_id,
            "allow_ssh": True,
        },
    )
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "user_id": str(operator["id"]),
            "asset_id": str(expired_asset["id"]),
            "credential_id": credential_id,
            "allow_ssh": True,
            "valid_until": (_now() - timedelta(days=1)).isoformat(),
        },
    )

    operator_token = await _login(client, username="operator3")
    response = await client.get("/api/pam/my-access", headers={"Authorization": f"Bearer {operator_token}"})

    assert response.status_code == 200
    body = response.json()
    hostnames = [row["asset_hostname"] for row in body]
    assert hostnames == ["active.example.local"]
    # Faz 58 — `_seed_asset` varsayılanı `status="up"`, yeni bir aktif
    # oturum açılmadı: dürüstçe çevrimiçi + sıfır aktif bağlantı.
    assert body[0]["is_online"] is True
    assert body[0]["active_sessions_count"] == 0


@pytest.mark.anyio
async def test_my_access_reports_offline_asset_honestly(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator-offline", role="OPERATOR")
    offline_asset = await _seed_asset(isolated_db, ip_address="10.0.9.60", hostname="offline.example.local", status="down")
    credential_id = (
        await client.post(
            "/api/pam/vault",
            headers=headers,
            json={"name": "offline-cred", "credential_type": "password", "username": "root", "password": "x"},
        )
    ).json()["id"]
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={"user_id": str(operator["id"]), "asset_id": str(offline_asset["id"]), "credential_id": credential_id, "allow_ssh": True},
    )

    operator_token = await _login(client, username="operator-offline")
    response = await client.get("/api/pam/my-access", headers={"Authorization": f"Bearer {operator_token}"})

    assert response.status_code == 200
    assert response.json()[0]["is_online"] is False


@pytest.mark.anyio
async def test_my_access_reflects_real_active_session_count(isolated_db, client):
    from app.pam import session_registry

    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator-live", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.61", hostname="live.example.local")
    credential_id = (
        await client.post(
            "/api/pam/vault",
            headers=headers,
            json={"name": "live-cred", "credential_type": "password", "username": "root", "password": "x"},
        )
    ).json()["id"]
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={"user_id": str(operator["id"]), "asset_id": str(asset["id"]), "credential_id": credential_id, "allow_ssh": True},
    )
    operator_token = await _login(client, username="operator-live")

    # `pam_session_logs`'a GERÇEK bir canlı oturum satırı düşürülür ve
    # Faz 51'in çapraz kontrolünü geçmesi için `session_registry`'ye de
    # kaydedilir (yalnızca `ended_at IS NULL` yeterli değil).
    from app.db.pam import close_session_log, insert_session_log

    session_row = await insert_session_log(
        isolated_db,
        user_id=operator["id"],
        asset_id=asset["id"],
        credential_id=None,
        protocol="ssh",
        client_ip="127.0.0.1",
    )
    session_registry.register(session_row["id"])
    try:
        response = await client.get("/api/pam/my-access", headers={"Authorization": f"Bearer {operator_token}"})
        assert response.status_code == 200
        assert response.json()[0]["active_sessions_count"] == 1
    finally:
        session_registry.unregister(session_row["id"])
        await close_session_log(isolated_db, session_row["id"], end_reason="user_closed")


@pytest.mark.anyio
async def test_audit_log_requires_admin(isolated_db, client):
    await _seed_user(isolated_db, username="viewer2", role="VIEWER")
    token = await _login(client, username="viewer2")

    response = await client.get("/api/pam/audit", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


@pytest.mark.anyio
async def test_audit_log_lists_no_sessions_for_a_freshly_created_user(isolated_db, client):
    """`isolated_db` yalnızca BU testin YAZDIĞI satırları rollback eder
    — bu artık gerçekten kullanılan (`GET /api/pam/audit` gerçek
    kullanıcılar tarafından tetiklenen gerçek SSH/RDP oturumları
    içerebilir) canlı bir veritabanına karşı çalıştığı için, genel
    listenin TAMAMEN boş olduğu VARSAYILAMAZ — bunun yerine bu testte
    YENİ oluşturulan (dolayısıyla hiç oturum geçmişi OLAMAYACAK) bir
    kullanıcı için hiçbir kayıt görünmediği doğrulanır."""
    headers = await _admin_headers(isolated_db, client)
    fresh_user = await _seed_user(isolated_db, username="audit-fresh-user", role="OPERATOR")

    response = await client.get("/api/pam/audit", headers=headers)

    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert all(entry["user_id"] != str(fresh_user["id"]) for entry in response.json())


# ---- Faz 47 — ince taneli izinler ------------------------------------------


@pytest.mark.anyio
async def test_login_response_includes_default_permissions_for_role(isolated_db, client):
    await _seed_user(isolated_db, username="operator-perms", role="OPERATOR")

    response = await client.post("/api/auth/login", json={"username": "operator-perms", "password": "s3cret-pw!"})

    assert response.status_code == 200
    permissions = response.json()["user"]["permissions"]
    assert "PAM_ACCESS" in permissions
    assert "PAM_ADMIN" not in permissions
    assert "DASHBOARD_VIEW" in permissions


@pytest.mark.anyio
async def test_admin_can_restrict_user_to_pam_access_only(isolated_db, client):
    """Kullanıcının açık örneği: bir kullanıcıya yalnızca `PAM_ACCESS`
    bırakılıp Dashboard dahil her genel menüden mahrum bırakılabilmesi."""
    headers = await _admin_headers(isolated_db, client)
    restricted = await _seed_user(isolated_db, username="pam-only", role="OPERATOR")

    update_response = await client.put(
        f"/api/pam/users/{restricted['id']}/permissions",
        headers=headers,
        json={"permissions": ["PAM_ACCESS"]},
    )
    assert update_response.status_code == 200
    assert update_response.json()["permissions"] == ["PAM_ACCESS"]

    token = await _login(client, username="pam-only")
    me_response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.json()["permissions"] == ["PAM_ACCESS"]

    # PAM_ACCESS sayesinde my-access erişilebilir...
    my_access_response = await client.get("/api/pam/my-access", headers={"Authorization": f"Bearer {token}"})
    assert my_access_response.status_code == 200
    # ...ama PAM_ADMIN gerektiren hiçbir ekrana (ör. kullanıcı listesi) erişemez.
    users_response = await client.get("/api/pam/users", headers={"Authorization": f"Bearer {token}"})
    assert users_response.status_code == 403


@pytest.mark.anyio
async def test_permission_override_grants_pam_admin_without_admin_role(isolated_db, client):
    """İzin modeli role'den BAĞIMSIZ override edilebilir — bir OPERATOR
    açıkça `PAM_ADMIN` verilirse PAM yönetim ekranlarına erişebilir."""
    admin_headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator-promoted", role="OPERATOR")

    await client.put(
        f"/api/pam/users/{operator['id']}/permissions",
        headers=admin_headers,
        json={"permissions": ["PAM_ACCESS", "PAM_ADMIN"]},
    )
    token = await _login(client, username="operator-promoted")

    response = await client.get("/api/pam/users", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200


@pytest.mark.anyio
async def test_revoking_pam_access_blocks_ssh_even_with_existing_rule(isolated_db, client):
    """`PAM_ACCESS` izni geri alınırsa, kullanıcının eski `pam_access_
    rules` satırı hâlâ dursa bile PAM SSH bağlantısı reddedilir (bkz.
    `app/routes/pam_ssh.py` — izin + kural İKİSİ birden gerekir)."""
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator-revoked", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.30")
    credential_response = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "srv7-root", "credential_type": "password", "username": "root", "password": "hunter2"},
    )
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "user_id": str(operator["id"]),
            "asset_id": str(asset["id"]),
            "credential_id": credential_response.json()["id"],
            "allow_ssh": True,
        },
    )

    # PAM_ACCESS izni kaldırılıyor (yalnızca genel view izinleri kalıyor).
    await client.put(
        f"/api/pam/users/{operator['id']}/permissions",
        headers=headers,
        json={"permissions": ["DASHBOARD_VIEW"]},
    )

    token = await _login(client, username="operator-revoked")
    my_access_response = await client.get("/api/pam/my-access", headers={"Authorization": f"Bearer {token}"})
    assert my_access_response.status_code == 403


# ---- Faz 48 — RDP yetkilendirmesi (artık guacd'ye enjekte edilen tam ----
# ---- kimlik bilgisi döner, .rdp dosyası akışı KALDIRILDI) ----------------


@pytest.mark.anyio
async def test_authorize_rdp_session_returns_decrypted_credential_for_guacd(isolated_db, client):
    from app.pam.service import authorize_rdp_session

    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator-rdp3", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.33")
    credential_response = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={
            "name": "srv10-admin",
            "credential_type": "password",
            "username": "Administrator",
            "domain": "CORP",
            "password": "hunter2",
        },
    )
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "user_id": str(operator["id"]),
            "asset_id": str(asset["id"]),
            "credential_id": credential_response.json()["id"],
            "allow_rdp": True,
            "max_session_duration_mins": 45,
        },
    )

    authorization = await authorize_rdp_session(isolated_db, user_id=operator["id"], asset_id=asset["id"])

    assert authorization.username == "Administrator"
    assert authorization.password == "hunter2"
    assert authorization.domain == "CORP"
    assert authorization.max_session_duration_mins == 45


@pytest.mark.anyio
async def test_authorize_rdp_session_rejects_when_allow_rdp_false(isolated_db, client):
    from app.pam.service import SshNotAuthorizedError, authorize_rdp_session

    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator-rdp4", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.34")
    credential_response = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "srv11-admin", "credential_type": "password", "username": "Administrator", "password": "x"},
    )
    await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "user_id": str(operator["id"]),
            "asset_id": str(asset["id"]),
            "credential_id": credential_response.json()["id"],
            "allow_ssh": True,
            "allow_rdp": False,
        },
    )

    with pytest.raises(SshNotAuthorizedError):
        await authorize_rdp_session(isolated_db, user_id=operator["id"], asset_id=asset["id"])


# ---- Faz 54 — "Aktif/Pasif" anahtarı + arama/filtre --------------------------


@pytest.mark.anyio
async def test_deactivated_rule_blocks_ssh_authorization(isolated_db, client):
    """`is_active=false` yalnızca kozmetik değil — kural SİLİNMEDEN
    erişim GERÇEKTEN reddedilir."""
    from app.pam.service import SshNotAuthorizedError, authorize_ssh_session

    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator-toggle1", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.40")
    credential_response = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "srv12-root", "credential_type": "password", "username": "root", "password": "x"},
    )
    create_response = await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "user_id": str(operator["id"]),
            "asset_id": str(asset["id"]),
            "credential_id": credential_response.json()["id"],
            "allow_ssh": True,
        },
    )
    rule_id = create_response.json()["id"]

    # Etkinken erişim çalışır.
    await authorize_ssh_session(isolated_db, user_id=operator["id"], asset_id=asset["id"])

    update_response = await client.put(f"/api/pam/rules/{rule_id}", headers=headers, json={"is_active": False})
    assert update_response.status_code == 200
    assert update_response.json()["is_active"] is False

    with pytest.raises(SshNotAuthorizedError):
        await authorize_ssh_session(isolated_db, user_id=operator["id"], asset_id=asset["id"])


@pytest.mark.anyio
async def test_deactivated_rule_excluded_from_my_access(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator-toggle2", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.41", hostname="toggle-target.example.local")
    credential_response = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "srv13-root", "credential_type": "password", "username": "root", "password": "x"},
    )
    create_response = await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "user_id": str(operator["id"]),
            "asset_id": str(asset["id"]),
            "credential_id": credential_response.json()["id"],
            "allow_ssh": True,
        },
    )
    rule_id = create_response.json()["id"]
    await client.put(f"/api/pam/rules/{rule_id}", headers=headers, json={"is_active": False})

    operator_token = await _login(client, username="operator-toggle2")
    response = await client.get("/api/pam/my-access", headers={"Authorization": f"Bearer {operator_token}"})

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_new_rule_defaults_to_active(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="operator-toggle3", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.42")
    credential_response = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "srv14-root", "credential_type": "password", "username": "root", "password": "x"},
    )

    response = await client.post(
        "/api/pam/rules",
        headers=headers,
        json={
            "user_id": str(operator["id"]),
            "asset_id": str(asset["id"]),
            "credential_id": credential_response.json()["id"],
            "allow_ssh": True,
        },
    )

    assert response.json()["is_active"] is True


@pytest.mark.anyio
async def test_list_rules_search_filters_by_username(isolated_db, client):
    headers = await _admin_headers(isolated_db, client)
    operator = await _seed_user(isolated_db, username="search-target-user", role="OPERATOR")
    other = await _seed_user(isolated_db, username="unrelated-user", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.43")
    credential_response = await client.post(
        "/api/pam/vault",
        headers=headers,
        json={"name": "srv15-root", "credential_type": "password", "username": "root", "password": "x"},
    )
    credential_id = credential_response.json()["id"]
    for user in (operator, other):
        await client.post(
            "/api/pam/rules",
            headers=headers,
            json={
                "user_id": str(user["id"]),
                "asset_id": str(asset["id"]),
                "credential_id": credential_id,
                "allow_ssh": True,
            },
        )

    response = await client.get("/api/pam/rules", headers=headers, params={"search": "search-target"})

    assert response.status_code == 200
    usernames = [row["username"] for row in response.json()]
    assert usernames == ["search-target-user"]


@pytest.mark.anyio
async def test_list_audit_search_filters_by_username(isolated_db, client):
    """Gerçek bir oturum kaydı olmadan (WebSocket/guacd gerektirmez) —
    `insert_session_log` doğrudan çağrılarak arama filtresi izole test
    edilir."""
    from app.db.pam import insert_session_log

    headers = await _admin_headers(isolated_db, client)
    target_user = await _seed_user(isolated_db, username="audit-search-target", role="OPERATOR")
    other_user = await _seed_user(isolated_db, username="audit-search-other", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.44")
    await insert_session_log(
        isolated_db, user_id=target_user["id"], asset_id=asset["id"], credential_id=None, protocol="ssh", client_ip="10.0.0.9"
    )
    await insert_session_log(
        isolated_db, user_id=other_user["id"], asset_id=asset["id"], credential_id=None, protocol="ssh", client_ip="10.0.0.9"
    )

    response = await client.get("/api/pam/audit", headers=headers, params={"search": "audit-search-target"})

    assert response.status_code == 200
    usernames = [row["username"] for row in response.json()]
    assert usernames == ["audit-search-target"]


@pytest.mark.anyio
async def test_list_audit_protocol_filter(isolated_db, client):
    from app.db.pam import insert_session_log

    headers = await _admin_headers(isolated_db, client)
    user = await _seed_user(isolated_db, username="audit-protocol-user", role="OPERATOR")
    asset = await _seed_asset(isolated_db, ip_address="10.0.9.45")
    await insert_session_log(
        isolated_db, user_id=user["id"], asset_id=asset["id"], credential_id=None, protocol="ssh", client_ip="10.0.0.9"
    )
    await insert_session_log(
        isolated_db, user_id=user["id"], asset_id=asset["id"], credential_id=None, protocol="rdp", client_ip="10.0.0.9"
    )

    response = await client.get("/api/pam/audit", headers=headers, params={"search": "audit-protocol-user", "protocol": "rdp"})

    assert response.status_code == 200
    protocols = [row["protocol"] for row in response.json()]
    assert protocols == ["rdp"]

