from unittest.mock import AsyncMock, patch

import pytest

# `/api/health/snmp` artık gerçekten `snmp_profiles` tablosunu okuyor
# (bkz. Faz: "SNMP Durumu" gerçek profil varlığını yansıtmalı) — bu
# yüzden bu dosyadaki TÜM testler `isolated_db`/`client` (async, izole
# transaction) kullanır, sync `TestClient` DEĞİL (bkz. `docs/
# decisions.md` §11 — event loop uyuşmazlığı + gerçek veriye dokunma
# riski). `/api/health` DB'ye hiç dokunmasa da tutarlılık için aynı
# desende tutuldu.


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
        community_ref="public",
    )
    payload.update(overrides)
    return payload


@pytest.mark.anyio
async def test_health_returns_status_ok(client):
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_health_snmp_returns_not_configured_when_no_profiles_exist(client):
    response = await client.get("/api/health/snmp")

    assert response.status_code == 200
    assert response.json() == {"snmp": "not_configured"}


@pytest.mark.anyio
async def test_health_snmp_returns_not_configured_when_only_disabled_profiles_exist(client):
    await client.post("/api/snmp/profiles", json=_v2c_payload(enabled=False))

    response = await client.get("/api/health/snmp")

    assert response.json() == {"snmp": "not_configured"}


@pytest.mark.anyio
async def test_health_snmp_returns_configured_when_a_ready_profile_exists(client):
    # `community_ref="public"` bir `.env` değişkeni olarak bulunamasa
    # bile artık düz metin community string olarak kabul edildiği için
    # (bkz. secrets.py) profil dürüstçe "ready" olur.
    await client.post("/api/snmp/profiles", json=_v2c_payload())

    response = await client.get("/api/health/snmp")

    assert response.json() == {"snmp": "configured"}


@pytest.mark.anyio
async def test_health_snmp_returns_not_configured_when_database_unreachable(client):
    with patch(
        "app.routes.health.get_connection",
        AsyncMock(side_effect=OSError("connection refused")),
    ):
        response = await client.get("/api/health/snmp")

    assert response.status_code == 200
    assert response.json() == {"snmp": "not_configured"}
