"""SNMP Profile Configuration Center API için gerçek PostgreSQL'e bağlı
testler (Faz 29). `isolated_db`/`client` sayesinde gerçek/kalıcı veriye
hiçbir etkisi yok. Gerçek bir SNMP ağ trafiği yalnızca "Test Connection"
testlerinde SÖZ KONUSU OLABİLİRDİ — o yüzden `SNMPClient.poll_asset`
HER ZAMAN mock'lanır, hiçbir gerçek UDP paketi gönderilmez."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.db.assets import upsert_asset
from app.snmp.models import SNMPPollResult, SystemInfo


@pytest.fixture(autouse=True)
async def _clean_snmp_profiles_table(isolated_db):
    await isolated_db.execute("TRUNCATE TABLE snmp_profiles, assets CASCADE")


async def _seed_asset(isolated_db, **overrides) -> dict:
    defaults = dict(
        ip_address="10.0.213.254",
        hostname="fw01",
        mac_address=None,
        vendor=None,
        device_type="firewall",
        confidence="medium",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return await upsert_asset(isolated_db, **defaults)


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
async def test_create_v2c_profile_is_ready_with_plain_text_community(client, monkeypatch):
    """`community_ref` bir `.env` değişkeni olarak TANIMLI DEĞİLSE bile
    artık `not_configured`'a düşmek yerine düz metin community string
    olarak kabul edilir (kullanıcı isteği — bkz. `secrets.py::
    resolve_secret` `allow_literal_fallback`). Eskiden bu profil
    sürekli "Yapılandırılmadı" gösteriyordu."""
    monkeypatch.delenv("SNMP_CORE_SWITCH_COMMUNITY", raising=False)

    response = await client.post("/api/snmp/profiles", json=_v2c_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Core Switches"
    assert body["credential_configured"] is True
    assert body["status"] == "ready"
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
async def test_test_connection_uses_literal_community_when_not_an_env_var(client, monkeypatch):
    """`community_ref` bir `.env` değişkeni olarak bulunamıyorsa artık
    `not_configured`'a düşmek yerine metnin kendisi community string
    olarak kullanılarak GERÇEKTEN bir poll denenir (burada mock'lanır —
    hiçbir gerçek UDP paketi gönderilmez)."""
    monkeypatch.delenv("SNMP_CORE_SWITCH_COMMUNITY", raising=False)
    created = (await client.post("/api/snmp/profiles", json=_v2c_payload())).json()

    fake_result = SNMPPollResult(
        asset_id=created["id"],
        polled_at="2026-08-26T00:00:00Z",
        status="success",
        system=SystemInfo(
            sys_name="core-sw-01", sys_descr="Cisco IOS", sys_object_id="1.3.6.1.4.1.9", sys_uptime_ticks=100
        ),
    )
    with patch(
        "app.snmp.profile_service.SNMPClient.poll_asset", AsyncMock(return_value=fake_result)
    ) as poll_mock:
        response = await client.post(f"/api/snmp/profiles/{created['id']}/test")

    assert response.json()["status"] == "connected"
    poll_mock.assert_awaited_once()


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


# --- Auto-assign (kullanıcı isteği: target_host bir asset'in IP'siyle
# eşleşiyorsa profili o asset'e otomatik ata) ---


@pytest.mark.anyio
async def test_create_profile_auto_assigns_when_target_host_matches_asset_ip(client, isolated_db):
    asset = await _seed_asset(isolated_db, ip_address="10.0.213.254")

    response = await client.post(
        "/api/snmp/profiles", json=_v2c_payload(target_host="10.0.213.254")
    )

    assert response.status_code == 201
    assert response.json()["assigned_asset_count"] == 1
    assigned = await client.get(f"/api/assets/{asset['id']}/snmp-profile")
    assert assigned.json()["configured"] is True


@pytest.mark.anyio
async def test_create_profile_does_not_auto_assign_when_no_asset_matches(client):
    response = await client.post(
        "/api/snmp/profiles", json=_v2c_payload(target_host="10.0.213.254")
    )

    assert response.status_code == 201
    assert response.json()["assigned_asset_count"] == 0


@pytest.mark.anyio
async def test_create_profile_auto_assign_never_overwrites_an_existing_manual_assignment(
    client, isolated_db
):
    asset = await _seed_asset(isolated_db, ip_address="10.0.213.254")
    manual_profile = (
        await client.post(
            "/api/snmp/profiles", json=_v2c_payload(name="Manual", target_host="10.0.0.1")
        )
    ).json()
    await client.put(f"/api/assets/{asset['id']}/snmp-profile/{manual_profile['id']}")

    response = await client.post(
        "/api/snmp/profiles", json=_v2c_payload(name="Auto", target_host="10.0.213.254")
    )

    assert response.status_code == 201
    assert response.json()["assigned_asset_count"] == 0  # yeni profil atanmadı
    assigned = await client.get(f"/api/assets/{asset['id']}/snmp-profile")
    assert assigned.json()["profile"]["id"] == manual_profile["id"]  # elle yapılan atama korundu


@pytest.mark.anyio
async def test_update_profile_auto_assigns_when_new_target_host_matches_asset_ip(client, isolated_db):
    asset = await _seed_asset(isolated_db, ip_address="10.0.213.254")
    created = (
        await client.post("/api/snmp/profiles", json=_v2c_payload(target_host="10.0.0.1"))
    ).json()
    assert created["assigned_asset_count"] == 0

    response = await client.put(
        f"/api/snmp/profiles/{created['id']}", json=_v2c_payload(target_host="10.0.213.254")
    )

    assert response.json()["assigned_asset_count"] == 1
    assigned = await client.get(f"/api/assets/{asset['id']}/snmp-profile")
    assert assigned.json()["profile"]["id"] == created["id"]


@pytest.mark.anyio
async def test_successful_test_connection_auto_assigns_when_target_host_matches_asset_ip(
    client, isolated_db
):
    asset = await _seed_asset(isolated_db, ip_address="10.0.213.254")
    created = (
        await client.post("/api/snmp/profiles", json=_v2c_payload(target_host="10.0.213.254"))
    ).json()
    # `create_profile` zaten otomatik atamış olabilir — atamayı kaldırıp
    # yalnızca "Test Connection" akışının KENDİSİNİN de auto-assign
    # tetiklediğini izole doğrulamak için önce temizleniyor.
    await client.delete(f"/api/assets/{asset['id']}/snmp-profile")

    fake_result = SNMPPollResult(
        asset_id=created["id"],
        polled_at="2026-08-26T00:00:00Z",
        status="success",
        system=SystemInfo(sys_name="fw01"),
    )
    with patch("app.snmp.profile_service.SNMPClient.poll_asset", AsyncMock(return_value=fake_result)):
        response = await client.post(f"/api/snmp/profiles/{created['id']}/test")

    assert response.json()["status"] == "connected"
    assigned = await client.get(f"/api/assets/{asset['id']}/snmp-profile")
    assert assigned.json()["profile"]["id"] == created["id"]


# --- Eşleşen asset yokken "Test Connection" GERÇEKTEN bağlandıysa yeni
# bir asset oluşturur (kullanıcı bildirimi: ICMP'yi engelleyen bir
# firewall/switch Network Discovery ile ASLA asset olmuyordu, SNMP
# profili "Hazır"/"Bağlandı" görünse bile Monitoring'de hiç veri
# çıkmıyordu — çünkü arka plan poller'ı yalnızca MEVCUT asset'leri
# dolaşır). ---


@pytest.mark.anyio
async def test_test_connection_creates_asset_when_none_matches_and_connection_succeeds(client):
    created = (
        await client.post("/api/snmp/profiles", json=_v2c_payload(target_host="10.0.213.254"))
    ).json()
    assert created["assigned_asset_count"] == 0  # eşleşen bir asset yok

    fake_result = SNMPPollResult(
        asset_id=created["id"],
        polled_at="2026-08-26T00:00:00Z",
        status="success",
        system=SystemInfo(sys_name="PSL-HQ-70G-1.alb.local", sys_descr="FortiGate-70G v7.0"),
    )
    with patch("app.snmp.profile_service.SNMPClient.poll_asset", AsyncMock(return_value=fake_result)):
        response = await client.post(f"/api/snmp/profiles/{created['id']}/test")

    assert response.json()["status"] == "connected"

    assets = (await client.get("/api/assets")).json()
    matching = [a for a in assets if a["ip_address"] == "10.0.213.254"]
    assert len(matching) == 1
    new_asset = matching[0]
    assert new_asset["hostname"] == "PSL-HQ-70G-1.alb.local"
    assert new_asset["device_type"] == "firewall"  # sysDescr'deki "FortiGate"den çıkarıldı
    assert new_asset["confidence"] == "medium"
    assert new_asset["status"] == "up"

    assigned = await client.get(f"/api/assets/{new_asset['id']}/snmp-profile")
    assert assigned.json()["profile"]["id"] == created["id"]


@pytest.mark.anyio
async def test_test_connection_does_not_create_asset_when_connection_fails(client):
    created = (
        await client.post("/api/snmp/profiles", json=_v2c_payload(target_host="10.0.213.254"))
    ).json()

    fake_result = SNMPPollResult(
        asset_id=created["id"], polled_at="2026-08-26T00:00:00Z", status="timeout", error="zaman aşımı"
    )
    with patch("app.snmp.profile_service.SNMPClient.poll_asset", AsyncMock(return_value=fake_result)):
        await client.post(f"/api/snmp/profiles/{created['id']}/test")

    assets = (await client.get("/api/assets")).json()
    assert not any(a["ip_address"] == "10.0.213.254" for a in assets)


@pytest.mark.anyio
async def test_test_connection_defaults_to_network_device_when_sys_descr_gives_no_hint(client):
    created = (
        await client.post("/api/snmp/profiles", json=_v2c_payload(target_host="10.0.213.254"))
    ).json()

    fake_result = SNMPPollResult(
        asset_id=created["id"], polled_at="2026-08-26T00:00:00Z", status="success",
        system=SystemInfo(sys_name="mystery-device", sys_descr="Some Custom Firmware 1.0"),
    )
    with patch("app.snmp.profile_service.SNMPClient.poll_asset", AsyncMock(return_value=fake_result)):
        await client.post(f"/api/snmp/profiles/{created['id']}/test")

    assets = (await client.get("/api/assets")).json()
    matching = [a for a in assets if a["ip_address"] == "10.0.213.254"]
    assert matching[0]["device_type"] == "network_device"


@pytest.mark.anyio
async def test_test_connection_uses_profile_name_when_sys_descr_gives_no_hint(client):
    """Gerçek kullanıcı bildirimiyle bulunan bir senaryo: bir
    FortiGate'in sysDescr'i yalnızca kurum-içi bir adlandırma
    döndürüyordu ("PSL_HQ_FGT") — hiçbir üretici/cihaz anahtar kelimesi
    içermiyordu. Kullanıcının profile verdiği GERÇEK ad ("FW") ikinci
    bir sinyal olarak kullanılır."""
    created = (
        await client.post(
            "/api/snmp/profiles", json=_v2c_payload(name="FW", target_host="10.0.213.254")
        )
    ).json()

    fake_result = SNMPPollResult(
        asset_id=created["id"], polled_at="2026-08-26T00:00:00Z", status="success",
        system=SystemInfo(sys_name="PSL-HQ-70G-1.alb.local", sys_descr="PSL_HQ_FGT"),
    )
    with patch("app.snmp.profile_service.SNMPClient.poll_asset", AsyncMock(return_value=fake_result)):
        await client.post(f"/api/snmp/profiles/{created['id']}/test")

    assets = (await client.get("/api/assets")).json()
    matching = [a for a in assets if a["ip_address"] == "10.0.213.254"]
    assert matching[0]["device_type"] == "firewall"


@pytest.mark.anyio
async def test_create_profile_never_creates_an_asset_even_without_a_live_poll(client):
    """`create_profile`/`replace_profile` HİÇBİR ZAMAN canlı bir poll
    yapmaz — bu yüzden `confirmed_system` YOKTUR, bir asset asla
    UYDURULMAZ (yalnızca `test_connection`'ın GERÇEK bağlantı kanıtı
    asset oluşturabilir)."""
    response = await client.post(
        "/api/snmp/profiles", json=_v2c_payload(target_host="10.0.213.254")
    )
    assert response.json()["assigned_asset_count"] == 0

    assets = (await client.get("/api/assets")).json()
    assert not any(a["ip_address"] == "10.0.213.254" for a in assets)
