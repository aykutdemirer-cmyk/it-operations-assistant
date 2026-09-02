"""SNMP Profile Configuration Center API için gerçek PostgreSQL'e bağlı
testler (Faz 29). `isolated_db`/`client` sayesinde gerçek/kalıcı veriye
hiçbir etkisi yok. Gerçek bir SNMP ağ trafiği yalnızca "Test Connection"
testlerinde SÖZ KONUSU OLABİLİRDİ — o yüzden `SNMPClient.poll_asset`
HER ZAMAN mock'lanır, hiçbir gerçek UDP paketi gönderilmez."""

from unittest.mock import AsyncMock, patch

import pytest

from app.snmp.models import SNMPPollResult, SystemInfo


@pytest.fixture(autouse=True)
async def _clean_snmp_profiles_table(isolated_db):
    await isolated_db.execute("TRUNCATE TABLE snmp_profiles CASCADE")


def _v2c_payload(**overrides) -> dict:
    payload = dict(
        name="Core Switches",
        target_host="10.0.213.10",
        port=161,
        version="v2c",
        timeout_seconds=2.0,
        retries=2,
        enabled=True,
        community_ref="SNMP_CORE_SWITCH_COMMUNITY",
    )
    payload.update(overrides)
    return payload


def _v3_payload(**overrides) -> dict:
    payload = dict(
        name="Linux Network",
        target_host="10.0.213.20",
        port=161,
        version="v3",
        timeout_seconds=2.0,
        retries=1,
        enabled=True,
        username="monitoring",
    )
    payload.update(overrides)
    return payload


@pytest.mark.anyio
async def test_list_profiles_returns_empty_list_when_none_exist(client):
    response = await client.get("/api/snmp/profiles")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_create_v2c_profile_returns_201_without_secret(client, monkeypatch):
    monkeypatch.delenv("SNMP_CORE_SWITCH_COMMUNITY", raising=False)

    response = await client.post("/api/snmp/profiles", json=_v2c_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Core Switches"
    assert body["credential_configured"] is False
    assert body["status"] == "not_configured"
    forbidden_keys = {"community_string", "password", "secret", "auth_secret", "priv_secret"}
    assert forbidden_keys.isdisjoint(body.keys())


@pytest.mark.anyio
async def test_create_v2c_profile_is_ready_when_secret_resolves(client, monkeypatch):
    monkeypatch.setenv("SNMP_CORE_SWITCH_COMMUNITY", "gercek-topluluk-degeri")

    response = await client.post("/api/snmp/profiles", json=_v2c_payload())

    body = response.json()
    assert body["credential_configured"] is True
    assert body["status"] == "ready"
    assert "gercek-topluluk-degeri" not in response.text


@pytest.mark.anyio
async def test_create_v3_no_auth_no_priv_is_ready_without_any_secret(client):
    response = await client.post("/api/snmp/profiles", json=_v3_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["security_level"] == "noAuthNoPriv"
    assert body["credential_configured"] is True
    assert body["status"] == "ready"


@pytest.mark.anyio
async def test_create_v3_auth_no_priv_not_configured_without_secret(client, monkeypatch):
    monkeypatch.delenv("SNMP_V3_AUTH", raising=False)

    response = await client.post(
        "/api/snmp/profiles",
        json=_v3_payload(auth_protocol="SHA256", auth_credential_ref="SNMP_V3_AUTH"),
    )

    body = response.json()
    assert body["security_level"] == "authNoPriv"
    assert body["credential_configured"] is False
    assert body["status"] == "not_configured"


@pytest.mark.anyio
async def test_create_v3_auth_priv_ready_when_both_secrets_resolve(client, monkeypatch):
    monkeypatch.setenv("SNMP_V3_AUTH", "auth-secret")
    monkeypatch.setenv("SNMP_V3_PRIV", "priv-secret")

    response = await client.post(
        "/api/snmp/profiles",
        json=_v3_payload(
            auth_protocol="SHA256",
            auth_credential_ref="SNMP_V3_AUTH",
            priv_protocol="AES256",
            priv_credential_ref="SNMP_V3_PRIV",
        ),
    )

    body = response.json()
    assert body["security_level"] == "authPriv"
    assert body["credential_configured"] is True
    assert body["status"] == "ready"
    assert "auth-secret" not in response.text
    assert "priv-secret" not in response.text


@pytest.mark.anyio
async def test_disabled_profile_reports_disabled_status_even_with_secret(client, monkeypatch):
    monkeypatch.setenv("SNMP_CORE_SWITCH_COMMUNITY", "value")

    response = await client.post("/api/snmp/profiles", json=_v2c_payload(enabled=False))

    assert response.json()["status"] == "disabled"


@pytest.mark.anyio
async def test_create_duplicate_name_returns_409(client):
    await client.post("/api/snmp/profiles", json=_v2c_payload())
    response = await client.post("/api/snmp/profiles", json=_v2c_payload(target_host="10.0.213.99"))

    assert response.status_code == 409


@pytest.mark.anyio
async def test_create_rejects_invalid_port(client):
    response = await client.post("/api/snmp/profiles", json=_v2c_payload(port=70000))
    assert response.status_code == 422


@pytest.mark.anyio
async def test_create_rejects_invalid_timeout(client):
    response = await client.post("/api/snmp/profiles", json=_v2c_payload(timeout_seconds=-1))
    assert response.status_code == 422


@pytest.mark.anyio
async def test_create_rejects_negative_retries(client):
    response = await client.post("/api/snmp/profiles", json=_v2c_payload(retries=-1))
    assert response.status_code == 422


@pytest.mark.anyio
async def test_create_rejects_v2c_without_community_ref(client):
    response = await client.post("/api/snmp/profiles", json=_v2c_payload(community_ref=None))
    assert response.status_code == 422


@pytest.mark.anyio
async def test_get_profile_by_id(client):
    created = (await client.post("/api/snmp/profiles", json=_v2c_payload())).json()

    response = await client.get(f"/api/snmp/profiles/{created['id']}")

    assert response.status_code == 200
    assert response.json()["name"] == "Core Switches"


@pytest.mark.anyio
async def test_get_unknown_profile_returns_404(client):
    response = await client.get("/api/snmp/profiles/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_update_profile_replaces_fields(client):
    created = (await client.post("/api/snmp/profiles", json=_v2c_payload())).json()

    response = await client.put(
        f"/api/snmp/profiles/{created['id']}", json=_v2c_payload(name="Core Switches Updated", port=1161)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Core Switches Updated"
    assert body["port"] == 1161
    assert body["id"] == created["id"]


@pytest.mark.anyio
async def test_update_unknown_profile_returns_404(client):
    response = await client.put(
        "/api/snmp/profiles/00000000-0000-0000-0000-000000000000", json=_v2c_payload()
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_update_to_duplicate_name_returns_409(client):
    await client.post("/api/snmp/profiles", json=_v2c_payload(name="Profile A", target_host="10.0.0.1"))
    profile_b = (
        await client.post("/api/snmp/profiles", json=_v2c_payload(name="Profile B", target_host="10.0.0.2"))
    ).json()

    response = await client.put(
        f"/api/snmp/profiles/{profile_b['id']}", json=_v2c_payload(name="Profile A", target_host="10.0.0.2")
    )

    assert response.status_code == 409


@pytest.mark.anyio
async def test_delete_profile_removes_it(client):
    created = (await client.post("/api/snmp/profiles", json=_v2c_payload())).json()

    delete_response = await client.delete(f"/api/snmp/profiles/{created['id']}")
    get_response = await client.get(f"/api/snmp/profiles/{created['id']}")

    assert delete_response.status_code == 204
    assert get_response.status_code == 404


@pytest.mark.anyio
async def test_delete_unknown_profile_returns_404(client):
    response = await client.delete("/api/snmp/profiles/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_list_profiles_never_leaks_secret_value(client, monkeypatch):
    monkeypatch.setenv("SNMP_CORE_SWITCH_COMMUNITY", "asla-gorunmemesi-gereken-deger")
    await client.post("/api/snmp/profiles", json=_v2c_payload())

    response = await client.get("/api/snmp/profiles")

    assert "asla-gorunmemesi-gereken-deger" not in response.text


@pytest.mark.anyio
async def test_test_connection_returns_not_configured_when_disabled(client):
    created = (await client.post("/api/snmp/profiles", json=_v2c_payload(enabled=False))).json()

    response = await client.post(f"/api/snmp/profiles/{created['id']}/test")

    assert response.status_code == 200
    assert response.json()["status"] == "not_configured"


@pytest.mark.anyio
async def test_test_connection_returns_not_configured_when_secret_missing(client, monkeypatch):
    monkeypatch.delenv("SNMP_CORE_SWITCH_COMMUNITY", raising=False)
    created = (await client.post("/api/snmp/profiles", json=_v2c_payload())).json()

    response = await client.post(f"/api/snmp/profiles/{created['id']}/test")

    assert response.json()["status"] == "not_configured"


@pytest.mark.anyio
async def test_test_connection_reports_connected_with_system_info(client, monkeypatch):
    monkeypatch.setenv("SNMP_CORE_SWITCH_COMMUNITY", "value")
    created = (await client.post("/api/snmp/profiles", json=_v2c_payload())).json()

    fake_result = SNMPPollResult(
        asset_id=created["id"],
        polled_at="2026-08-26T00:00:00Z",
        status="success",
        system=SystemInfo(sys_name="core-sw-01", sys_descr="Cisco IOS", sys_object_id="1.3.6.1.4.1.9", sys_uptime_ticks=100),
    )
    with patch("app.snmp.profile_service.SNMPClient.poll_asset", AsyncMock(return_value=fake_result)):
        response = await client.post(f"/api/snmp/profiles/{created['id']}/test")

    body = response.json()
    assert body["status"] == "connected"
    assert body["sys_name"] == "core-sw-01"


@pytest.mark.anyio
async def test_test_connection_reports_timeout_honestly(client, monkeypatch):
    monkeypatch.setenv("SNMP_CORE_SWITCH_COMMUNITY", "value")
    created = (await client.post("/api/snmp/profiles", json=_v2c_payload())).json()

    fake_result = SNMPPollResult(
        asset_id=created["id"], polled_at="2026-08-26T00:00:00Z", status="timeout", error="SNMP isteği zaman aşımına uğradı"
    )
    with patch("app.snmp.profile_service.SNMPClient.poll_asset", AsyncMock(return_value=fake_result)):
        response = await client.post(f"/api/snmp/profiles/{created['id']}/test")

    assert response.json()["status"] == "timeout"


@pytest.mark.anyio
async def test_test_connection_unknown_profile_returns_404(client):
    response = await client.post("/api/snmp/profiles/00000000-0000-0000-0000-000000000000/test")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_profiles_returns_503_when_database_unreachable(client):
    with patch(
        "app.routes.snmp_profiles.get_connection",
        AsyncMock(side_effect=OSError("connection refused")),
    ):
        response = await client.get("/api/snmp/profiles")

    assert response.status_code == 503
    assert response.json()["detail"] == {"database": "unreachable"}
