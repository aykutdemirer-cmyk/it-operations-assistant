"""Agent Commands API için gerçek PostgreSQL'e bağlı testler (Faz 33).

`isolated_db`/`client` sayesinde gerçek/kalıcı veriye hiçbir etkisi
yok — her testin transaction'ı rollback ile biter."""

import pytest


@pytest.fixture(autouse=True)
async def _clean_tables(isolated_db):
    await isolated_db.execute(
        "TRUNCATE TABLE agent_commands, agent_telemetry, agent_inventory, agents, assets CASCADE"
    )


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
async def test_create_command_starts_pending(client):
    agent = await _register(client)
    response = await client.post(
        f"/api/agents/{agent['agent_id']}/commands",
        json={"command_type": "kill_process", "action": "kill", "target": "1234"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["target"] == "1234"


@pytest.mark.anyio
async def test_create_check_updates_command_starts_pending(client):
    """Windows Update Tarama Motoru — "Güncellemeleri Kontrol Et" butonu
    mevcut agent_commands kuyruğunu AYNEN kullanır."""
    agent = await _register(client)
    response = await client.post(
        f"/api/agents/{agent['agent_id']}/commands",
        json={"command_type": "check_updates", "action": "scan", "target": "self"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["command_type"] == "check_updates"
    assert body["action"] == "scan"


@pytest.mark.anyio
async def test_create_check_updates_command_rejects_mismatched_action(client):
    agent = await _register(client)
    response = await client.post(
        f"/api/agents/{agent['agent_id']}/commands",
        json={"command_type": "check_updates", "action": "kill", "target": "self"},
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_create_install_update_command_starts_pending(client):
    """Windows Update Yükleme — "Şimdi Yükle"/"Tümünü Yükle" butonları
    mevcut agent_commands kuyruğunu AYNEN kullanır."""
    agent = await _register(client)
    response = await client.post(
        f"/api/agents/{agent['agent_id']}/commands",
        json={"command_type": "install_update", "action": "install", "target": "KB5001234"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["command_type"] == "install_update"
    assert body["target"] == "KB5001234"


@pytest.mark.anyio
async def test_create_install_update_command_accepts_all_target(client):
    agent = await _register(client)
    response = await client.post(
        f"/api/agents/{agent['agent_id']}/commands",
        json={"command_type": "install_update", "action": "install", "target": "all"},
    )
    assert response.status_code == 201
    assert response.json()["target"] == "all"


@pytest.mark.anyio
async def test_create_install_update_command_rejects_mismatched_action(client):
    agent = await _register(client)
    response = await client.post(
        f"/api/agents/{agent['agent_id']}/commands",
        json={"command_type": "install_update", "action": "kill", "target": "KB5001234"},
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_create_command_rejects_mismatched_action(client):
    agent = await _register(client)
    response = await client.post(
        f"/api/agents/{agent['agent_id']}/commands",
        json={"command_type": "kill_process", "action": "restart", "target": "1234"},
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_create_command_rejects_known_system_pid(client):
    agent = await _register(client)
    response = await client.post(
        f"/api/agents/{agent['agent_id']}/commands",
        json={"command_type": "kill_process", "action": "kill", "target": "4"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "rejected"
    assert "sistem" in body["result_detail"].lower()


@pytest.mark.anyio
async def test_create_command_for_unknown_agent_returns_404(client):
    import uuid

    response = await client.post(
        f"/api/agents/{uuid.uuid4()}/commands",
        json={"command_type": "service_control", "action": "start", "target": "spooler"},
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_pending_commands_requires_bearer_token(client):
    agent = await _register(client)
    response = await client.get(f"/api/agents/{agent['agent_id']}/commands/pending")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_pending_commands_rejects_mismatched_agent_token(client):
    agent_a = await _register(client, hostname="a")
    agent_b = await _register(client, hostname="b", local_ip="10.0.5.11", mac_address="AA-BB-CC-DD-EE-11")

    response = await client.get(
        f"/api/agents/{agent_b['agent_id']}/commands/pending",
        headers={"Authorization": f"Bearer {agent_a['token']}"},
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_agent_pulls_pending_command_and_it_moves_to_sent(client):
    agent = await _register(client)
    await client.post(
        f"/api/agents/{agent['agent_id']}/commands",
        json={"command_type": "service_control", "action": "restart", "target": "spooler"},
    )

    headers = {"Authorization": f"Bearer {agent['token']}"}
    pending = await client.get(f"/api/agents/{agent['agent_id']}/commands/pending", headers=headers)
    assert pending.status_code == 200
    commands = pending.json()["commands"]
    assert len(commands) == 1
    assert commands[0]["target"] == "spooler"

    # İkinci çekişte artık bekleyen komut yok.
    second_pull = await client.get(f"/api/agents/{agent['agent_id']}/commands/pending", headers=headers)
    assert second_pull.json()["commands"] == []


@pytest.mark.anyio
async def test_agent_reports_command_result(client):
    agent = await _register(client)
    created = await client.post(
        f"/api/agents/{agent['agent_id']}/commands",
        json={"command_type": "kill_process", "action": "kill", "target": "9999"},
    )
    command_id = created.json()["id"]
    headers = {"Authorization": f"Bearer {agent['token']}"}

    result = await client.post(
        f"/api/agents/{agent['agent_id']}/commands/{command_id}/result",
        json={"status": "succeeded", "result_detail": "PID 9999 sonlandırıldı"},
        headers=headers,
    )
    assert result.status_code == 200

    history = await client.get(f"/api/agents/{agent['agent_id']}/commands")
    updated = next(c for c in history.json() if c["id"] == command_id)
    assert updated["status"] == "succeeded"
    assert updated["result_detail"] == "PID 9999 sonlandırıldı"


@pytest.mark.anyio
async def test_agent_cannot_report_result_for_another_agents_command(client):
    agent_a = await _register(client, hostname="a")
    agent_b = await _register(client, hostname="b", local_ip="10.0.5.11", mac_address="AA-BB-CC-DD-EE-11")

    created = await client.post(
        f"/api/agents/{agent_a['agent_id']}/commands",
        json={"command_type": "kill_process", "action": "kill", "target": "9999"},
    )
    command_id = created.json()["id"]

    response = await client.post(
        f"/api/agents/{agent_b['agent_id']}/commands/{command_id}/result",
        json={"status": "succeeded"},
        headers={"Authorization": f"Bearer {agent_b['token']}"},
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_list_commands_history_orders_newest_first(client):
    agent = await _register(client)
    await client.post(
        f"/api/agents/{agent['agent_id']}/commands",
        json={"command_type": "kill_process", "action": "kill", "target": "1111"},
    )
    second = await client.post(
        f"/api/agents/{agent['agent_id']}/commands",
        json={"command_type": "kill_process", "action": "kill", "target": "2222"},
    )

    history = await client.get(f"/api/agents/{agent['agent_id']}/commands")
    assert history.json()[0]["id"] == second.json()["id"]
