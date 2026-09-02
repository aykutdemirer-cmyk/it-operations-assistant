"""Agent API için gerçek PostgreSQL'e bağlı testler (Faz 28).

`isolated_db`/`client` (bkz. kök `conftest.py`) sayesinde gerçek/kalıcı
veriye hiçbir etkisi yok — her testin transaction'ı rollback ile biter.
Gerçek bir agent/ajan süreci hiç çalıştırılmaz, yalnızca HTTP sözleşmesi
test edilir."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.db.assets import upsert_asset


@pytest.fixture(autouse=True)
async def _clean_agents_tables(isolated_db):
    await isolated_db.execute("TRUNCATE TABLE agent_telemetry, agent_inventory, agents, assets CASCADE")


async def _seed_asset(isolated_db, **overrides) -> dict:
    defaults = dict(
        ip_address="10.0.5.10",
        hostname="win-host-01",
        mac_address="AA-BB-CC-DD-EE-10",
        vendor=None,
        device_type="server",
        confidence="medium",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return await upsert_asset(isolated_db, **defaults)


def _registration_payload(**overrides) -> dict:
    payload = dict(
        hostname="win-host-01",
        os="windows",
        os_version="Windows Server 2022",
        architecture="x86_64",
        agent_version="1.0.0",
        local_ip="10.0.5.10",
        mac_address="AA-BB-CC-DD-EE-10",
        capabilities=["system", "cpu", "memory", "disk", "network"],
    )
    payload.update(overrides)
    return payload


async def _new_enrollment_code(client) -> str:
    response = await client.post("/api/agents/enrollment-codes")
    assert response.status_code == 201
    return response.json()["code"]


async def _register(client, **overrides) -> dict:
    if "enrollment_code" not in overrides:
        overrides["enrollment_code"] = await _new_enrollment_code(client)
    response = await client.post("/api/agents/register", json=_registration_payload(**overrides))
    assert response.status_code == 201
    return response.json()


@pytest.mark.anyio
async def test_register_returns_agent_id_and_token(client):
    body = await _register(client)

    assert "agent_id" in body
    assert "token" in body
    assert len(body["token"]) >= 32


@pytest.mark.anyio
async def test_create_enrollment_code_returns_code_and_expiry(client):
    response = await client.post("/api/agents/enrollment-codes")

    assert response.status_code == 201
    body = response.json()
    assert len(body["code"]) >= 11  # "XXX-XXX-XXX"
    assert "expires_at" in body


@pytest.mark.anyio
async def test_list_enrollment_codes_shows_only_active_codes(client):
    created = await _new_enrollment_code(client)

    active = (await client.get("/api/agents/enrollment-codes")).json()

    assert created in [c["code"] for c in active]


@pytest.mark.anyio
async def test_used_enrollment_code_no_longer_listed_as_active(client):
    await _register(client)  # bir kod üretir ve hemen tüketir

    active = (await client.get("/api/agents/enrollment-codes")).json()

    assert active == []


@pytest.mark.anyio
async def test_register_without_enrollment_code_is_rejected(client):
    payload = _registration_payload()  # enrollment_code YOK

    response = await client.post("/api/agents/register", json=payload)

    assert response.status_code == 422


@pytest.mark.anyio
async def test_register_with_unknown_enrollment_code_returns_401(client):
    response = await client.post(
        "/api/agents/register", json=_registration_payload(enrollment_code="ZZZ-ZZZ-ZZZ")
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_register_with_already_used_enrollment_code_returns_401(client):
    code = await _new_enrollment_code(client)
    await client.post("/api/agents/register", json=_registration_payload(enrollment_code=code))

    second = await client.post(
        "/api/agents/register", json=_registration_payload(hostname="second-host", enrollment_code=code)
    )

    assert second.status_code == 401
    # İkinci kayıt gerçekten oluşmadı — yalnızca ilk agent var.
    assert len((await client.get("/api/agents")).json()) == 1


@pytest.mark.anyio
async def test_register_with_expired_enrollment_code_returns_401(isolated_db, client):
    from datetime import datetime, timedelta, timezone

    from app.db.agent_enrollment import insert_code

    await isolated_db.execute("DELETE FROM agent_enrollment_codes")
    await insert_code(
        isolated_db, code="OLD-OLD-OLD1", expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
    )

    response = await client.post(
        "/api/agents/register", json=_registration_payload(enrollment_code="OLD-OLD-OLD1")
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_enrollment_code_is_case_insensitive_and_trims_whitespace(client):
    code = await _new_enrollment_code(client)

    response = await client.post(
        "/api/agents/register",
        json=_registration_payload(enrollment_code=f"  {code.lower()}  "),
    )

    assert response.status_code == 201


@pytest.mark.anyio
async def test_register_stores_and_returns_fqdn_in_detail(client):
    registered = await _register(client, fqdn="win-host-01.lab.local")

    detail = (await client.get(f"/api/agents/{registered['agent_id']}")).json()
    assert detail["fqdn"] == "win-host-01.lab.local"


@pytest.mark.anyio
async def test_register_without_fqdn_defaults_to_none(client):
    registered = await _register(client)

    detail = (await client.get(f"/api/agents/{registered['agent_id']}")).json()
    assert detail["fqdn"] is None


@pytest.mark.anyio
async def test_register_creates_agent_visible_in_list_with_unknown_status(client):
    registered = await _register(client, hostname="new-agent")

    response = await client.get("/api/agents")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == registered["agent_id"]
    assert body[0]["hostname"] == "new-agent"
    assert body[0]["status"] == "unknown"
    assert body[0]["last_heartbeat_at"] is None


@pytest.mark.anyio
async def test_register_token_never_appears_in_list_or_detail_response(client):
    registered = await _register(client)
    token = registered["token"]

    list_response = await client.get("/api/agents")
    detail_response = await client.get(f"/api/agents/{registered['agent_id']}")

    assert token not in list_response.text
    assert token not in detail_response.text
    assert "token" not in list_response.json()[0]
    assert "token" not in detail_response.json()


@pytest.mark.anyio
async def test_heartbeat_with_valid_token_marks_agent_online(client):
    registered = await _register(client)
    headers = {"Authorization": f"Bearer {registered['token']}"}

    response = await client.post(
        "/api/agents/heartbeat", json={"uptime_seconds": 3600.5}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "online"
    assert body["last_heartbeat_at"] is not None


@pytest.mark.anyio
async def test_heartbeat_without_token_returns_401(client):
    response = await client.post("/api/agents/heartbeat", json={"uptime_seconds": 1})

    assert response.status_code == 401


@pytest.mark.anyio
async def test_heartbeat_with_invalid_token_returns_401(client):
    response = await client.post(
        "/api/agents/heartbeat",
        json={"uptime_seconds": 1},
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_heartbeat_updates_agent_version_when_provided(client):
    registered = await _register(client, agent_version="1.0.0")
    headers = {"Authorization": f"Bearer {registered['token']}"}

    await client.post(
        "/api/agents/heartbeat",
        json={"uptime_seconds": 10, "agent_version": "1.1.0"},
        headers=headers,
    )

    detail = (await client.get(f"/api/agents/{registered['agent_id']}")).json()
    assert detail["agent_version"] == "1.1.0"


@pytest.mark.anyio
async def test_telemetry_with_valid_token_is_stored_and_retrievable(client):
    registered = await _register(client)
    agent_id = registered["agent_id"]
    headers = {"Authorization": f"Bearer {registered['token']}"}

    telemetry_payload = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "cpu_percent": 42.5,
        "memory_total_bytes": 16_000_000_000,
        "memory_used_bytes": 8_000_000_000,
        "memory_percent": 50.0,
        "disks": [
            {"device": "C:", "total_bytes": 500_000_000_000, "used_bytes": 100_000_000_000, "percent": 20.0}
        ],
        "network_interfaces": [
            {"name": "Ethernet0", "ip_address": "10.0.5.10", "state": "up", "rx_bytes": 100, "tx_bytes": 200}
        ],
        "sessions": [
            {"username": "Administrator", "session_name": "rdp-tcp#1", "status": "active", "logon_time": "9/2/2026 8:57 AM"}
        ],
        "last_logged_in_user": "Administrator",
        "active_sessions_count": 1,
    }

    response = await client.post(f"/api/agents/{agent_id}/telemetry", json=telemetry_payload, headers=headers)
    assert response.status_code == 200

    detail = (await client.get(f"/api/agents/{agent_id}")).json()
    assert detail["latest_telemetry"]["cpu_percent"] == 42.5
    assert detail["latest_telemetry"]["disks"][0]["device"] == "C:"
    assert detail["latest_telemetry"]["last_logged_in_user"] == "Administrator"
    assert detail["latest_telemetry"]["active_sessions_count"] == 1
    assert detail["latest_telemetry"]["sessions"][0]["username"] == "Administrator"


@pytest.mark.anyio
async def test_connect_rdp_returns_rdp_file_with_local_ip(client):
    registered = await _register(client)
    agent_id = registered["agent_id"]

    response = await client.get(f"/api/agents/{agent_id}/connect/rdp")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-rdp")
    assert "attachment" in response.headers["content-disposition"]
    assert "full address:s:10.0.5.10" in response.text


@pytest.mark.anyio
async def test_connect_rdp_returns_404_when_no_local_ip(client):
    registered = await _register(client, local_ip=None)

    response = await client.get(f"/api/agents/{registered['agent_id']}/connect/rdp")

    assert response.status_code == 404


@pytest.mark.anyio
async def test_connect_rdp_returns_404_for_unknown_agent(client):
    import uuid

    response = await client.get(f"/api/agents/{uuid.uuid4()}/connect/rdp")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_connect_rdp_includes_last_logged_in_user_when_known(client):
    registered = await _register(client)
    agent_id = registered["agent_id"]
    headers = {"Authorization": f"Bearer {registered['token']}"}
    await client.post(
        f"/api/agents/{agent_id}/telemetry",
        json={
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "last_logged_in_user": "jdoe",
            "active_sessions_count": 1,
            "sessions": [{"username": "jdoe", "status": "active"}],
        },
        headers=headers,
    )

    response = await client.get(f"/api/agents/{agent_id}/connect/rdp")
    assert "username:s:jdoe" in response.text


@pytest.mark.anyio
async def test_telemetry_for_mismatched_agent_id_returns_403(client):
    registered_a = await _register(client, hostname="agent-a")
    registered_b = await _register(client, hostname="agent-b")
    headers_a = {"Authorization": f"Bearer {registered_a['token']}"}

    response = await client.post(
        f"/api/agents/{registered_b['agent_id']}/telemetry",
        json={"collected_at": datetime.now(timezone.utc).isoformat()},
        headers=headers_a,
    )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_telemetry_without_token_returns_401(client):
    registered = await _register(client)

    response = await client.post(
        f"/api/agents/{registered['agent_id']}/telemetry",
        json={"collected_at": datetime.now(timezone.utc).isoformat()},
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_inventory_with_valid_token_is_stored_and_retrievable(client):
    registered = await _register(client)
    agent_id = registered["agent_id"]
    headers = {"Authorization": f"Bearer {registered['token']}"}

    inventory_payload = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "hardware": {"manufacturer": "Dell", "model": "PowerEdge R640", "cpu_cores": 8},
        "os": {"name": "Windows Server", "version": "2022", "architecture": "x86_64"},
        "software": [{"name": "PostgreSQL", "version": "16.15"}],
        "services": [{"name": "spooler", "display_name": "Print Spooler", "state": "running"}],
    }

    response = await client.post(f"/api/agents/{agent_id}/inventory", json=inventory_payload, headers=headers)
    assert response.status_code == 200

    detail = (await client.get(f"/api/agents/{agent_id}")).json()
    assert detail["inventory"]["hardware"]["manufacturer"] == "Dell"
    assert detail["inventory"]["software"][0]["name"] == "PostgreSQL"


@pytest.mark.anyio
async def test_inventory_stores_and_returns_process_list(client):
    """Faz 30 — `processes` additive alanı. Command-line argümanları
    modelde hiç YOK (yalnızca PID/isim/CPU/memory/kullanıcı/durum)."""
    registered = await _register(client)
    agent_id = registered["agent_id"]
    headers = {"Authorization": f"Bearer {registered['token']}"}

    inventory_payload = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "processes": [
            {"pid": 1234, "name": "postgres.exe", "cpu_percent": 1.2, "memory_percent": 3.4,
             "username": "SYSTEM", "status": "running"},
        ],
    }

    response = await client.post(f"/api/agents/{agent_id}/inventory", json=inventory_payload, headers=headers)
    assert response.status_code == 200

    detail = (await client.get(f"/api/agents/{agent_id}")).json()
    assert detail["inventory"]["processes"] == [
        {"pid": 1234, "name": "postgres.exe", "cpu_percent": 1.2, "memory_percent": 3.4,
         "username": "SYSTEM", "status": "running"},
    ]
    assert "cmdline" not in str(detail["inventory"]["processes"][0])


@pytest.mark.anyio
async def test_inventory_defaults_to_empty_process_list_when_omitted(client):
    registered = await _register(client)
    agent_id = registered["agent_id"]
    headers = {"Authorization": f"Bearer {registered['token']}"}

    await client.post(
        f"/api/agents/{agent_id}/inventory",
        json={"collected_at": datetime.now(timezone.utc).isoformat()},
        headers=headers,
    )

    detail = (await client.get(f"/api/agents/{agent_id}")).json()
    assert detail["inventory"]["processes"] == []


@pytest.mark.anyio
async def test_register_rejects_hostname_over_length_limit(client):
    payload = {
        "hostname": "x" * 300,
        "os": "linux",
        "agent_version": "1.0.0",
    }

    response = await client.post("/api/agents/register", json=payload)

    assert response.status_code == 422


@pytest.mark.anyio
async def test_inventory_upserts_replacing_previous_snapshot(client):
    registered = await _register(client)
    agent_id = registered["agent_id"]
    headers = {"Authorization": f"Bearer {registered['token']}"}

    await client.post(
        f"/api/agents/{agent_id}/inventory",
        json={"collected_at": datetime.now(timezone.utc).isoformat(), "software": [{"name": "old-app"}]},
        headers=headers,
    )
    await client.post(
        f"/api/agents/{agent_id}/inventory",
        json={"collected_at": datetime.now(timezone.utc).isoformat(), "software": [{"name": "new-app"}]},
        headers=headers,
    )

    detail = (await client.get(f"/api/agents/{agent_id}")).json()
    assert len(detail["inventory"]["software"]) == 1
    assert detail["inventory"]["software"][0]["name"] == "new-app"


@pytest.mark.anyio
async def test_get_agent_returns_404_for_unknown_id(client):
    response = await client.get("/api/agents/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


@pytest.mark.anyio
async def test_get_agents_returns_empty_list_when_no_agents(client):
    response = await client.get("/api/agents")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_agent_detail_has_no_telemetry_or_inventory_when_none_reported(client):
    registered = await _register(client)

    detail = (await client.get(f"/api/agents/{registered['agent_id']}")).json()

    assert detail["latest_telemetry"] is None
    assert detail["inventory"] is None


@pytest.mark.anyio
async def test_agent_becomes_offline_after_threshold_exceeded(isolated_db, client, monkeypatch):
    monkeypatch.setenv("AGENT_OFFLINE_THRESHOLD_SECONDS", "60")
    registered = await _register(client)
    headers = {"Authorization": f"Bearer {registered['token']}"}
    await client.post("/api/agents/heartbeat", json={"uptime_seconds": 1}, headers=headers)

    stale_time = datetime.now(timezone.utc) - timedelta(seconds=600)
    await isolated_db.execute(
        "UPDATE agents SET last_heartbeat_at = $1 WHERE id = $2", stale_time, registered["agent_id"]
    )

    detail = (await client.get(f"/api/agents/{registered['agent_id']}")).json()
    assert detail["status"] == "offline"


@pytest.mark.anyio
async def test_two_registrations_for_same_hostname_create_separate_agents(client):
    """Faz 28'de asset eşleştirme/duplicate-prevention YOK (bilinçli —
    bkz. Faz 29); bu test bugünkü gerçek davranışı belgeliyor."""
    first = await _register(client, hostname="dup-host")
    second = await _register(client, hostname="dup-host")

    assert first["agent_id"] != second["agent_id"]
    assert (await client.get("/api/agents")).json().__len__() == 2


@pytest.mark.anyio
async def test_register_returns_503_when_database_unreachable(client):
    with patch(
        "app.routes.agents.get_connection",
        AsyncMock(side_effect=OSError("connection refused")),
    ):
        response = await client.post(
            "/api/agents/register", json=_registration_payload(enrollment_code="ABC-DEF-123")
        )

    assert response.status_code == 503
    assert response.json()["detail"] == {"database": "unreachable"}


@pytest.mark.anyio
async def test_asset_match_returns_confirmed_for_two_signal_match(isolated_db, client):
    asset = await _seed_asset(isolated_db)
    registered = await _register(client)  # aynı hostname+ip ile kayıtlı

    response = await client.get(f"/api/agents/{registered['agent_id']}/asset-match")

    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == "confirmed"
    assert body["asset_id"] == str(asset["id"])


@pytest.mark.anyio
async def test_asset_match_returns_unmatched_when_no_assets_exist(client):
    registered = await _register(client)

    response = await client.get(f"/api/agents/{registered['agent_id']}/asset-match")

    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == "unmatched"
    assert body["asset_id"] is None


@pytest.mark.anyio
async def test_asset_match_never_writes_asset_id_by_itself(isolated_db, client):
    await _seed_asset(isolated_db)
    registered = await _register(client)

    await client.get(f"/api/agents/{registered['agent_id']}/asset-match")

    detail = (await client.get(f"/api/agents/{registered['agent_id']}")).json()
    assert detail["asset_id"] is None


@pytest.mark.anyio
async def test_confirm_asset_match_sets_asset_id(isolated_db, client):
    asset = await _seed_asset(isolated_db)
    registered = await _register(client)

    response = await client.post(
        f"/api/agents/{registered['agent_id']}/asset-match", json={"asset_id": str(asset["id"])}
    )

    assert response.status_code == 200
    assert response.json()["asset_id"] == str(asset["id"])

    detail = (await client.get(f"/api/agents/{registered['agent_id']}")).json()
    assert detail["asset_id"] == str(asset["id"])


@pytest.mark.anyio
async def test_confirm_asset_match_returns_404_for_unknown_asset(client):
    registered = await _register(client)

    response = await client.post(
        f"/api/agents/{registered['agent_id']}/asset-match",
        json={"asset_id": "00000000-0000-0000-0000-000000000000"},
    )

    assert response.status_code == 404


# --- Faz 37: Wake-on-LAN ---


@pytest.mark.anyio
async def test_wake_sends_magic_packet_to_known_mac(client, monkeypatch):
    registered = await _register(client)

    calls = []
    monkeypatch.setattr("app.routes.agents.send_magic_packet", lambda mac: calls.append(mac))

    response = await client.post(f"/api/agents/{registered['agent_id']}/wake")

    assert response.status_code == 200
    assert response.json() == {"status": "sent", "mac_address": "AA-BB-CC-DD-EE-10"}
    assert calls == ["AA-BB-CC-DD-EE-10"]


@pytest.mark.anyio
async def test_wake_returns_404_for_unknown_agent(client):
    import uuid

    response = await client.post(f"/api/agents/{uuid.uuid4()}/wake")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_wake_returns_404_when_no_mac_address(client):
    registered = await _register(client, mac_address=None)

    response = await client.post(f"/api/agents/{registered['agent_id']}/wake")

    assert response.status_code == 404


@pytest.mark.anyio
async def test_wake_never_requires_agent_to_be_online(client, monkeypatch):
    """WoL'un bütün amacı bu — agent'ın kendisiyle HİÇ konuşulmaz,
    yalnızca DB'deki MAC'e bir paket gönderilir."""
    registered = await _register(client)
    monkeypatch.setattr("app.routes.agents.send_magic_packet", lambda mac: None)

    # Bu agent hiçbir zaman heartbeat/telemetry göndermedi — durumu
    # gerçekte "unknown"/"offline" olurdu, yine de wake çağrısı başarılı olmalı.
    response = await client.post(f"/api/agents/{registered['agent_id']}/wake")

    assert response.status_code == 200
