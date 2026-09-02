"""`GET /api/monitoring` için gerçek PostgreSQL'e bağlı testler
(Faz 24). Gerçek SNMP ağ trafiği yok — `SNMPClient.poll_asset` mock'lanır
(bkz. `apps/api/tests/snmp/test_poller.py`'nin kendi mock'lanmış
testleri, burada yalnızca HTTP katmanı + gerçek DB entegrasyonu
doğrulanıyor). `isolated_db` (bkz. kök `conftest.py`) sayesinde
`TRUNCATE TABLE assets` çalışsa bile gerçek/kalıcı veriye hiçbir etkisi
yok — test transaction'ı rollback ile bitiyor."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.db.assets import upsert_asset
from app.snmp.models import SNMPPollResult


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
async def _clean_assets_table(isolated_db):
    await isolated_db.execute("TRUNCATE TABLE assets CASCADE")


async def _seed(isolated_db, **overrides) -> dict:
    defaults = dict(
        ip_address="10.0.9.20",
        hostname="switch2.example.local",
        mac_address="AA-BB-CC-DD-EE-02",
        vendor="Cisco Systems, Inc.",
        device_type="switch",
        confidence="medium",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )
    defaults.update(overrides)
    return await upsert_asset(isolated_db, **defaults)


@pytest.mark.anyio
async def test_monitoring_returns_empty_batch_when_no_assets(client):
    response = await client.get("/api/monitoring")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["polled"] == 0
    assert body["not_configured"] == 0
    assert body["results"] == []


@pytest.mark.anyio
async def test_monitoring_returns_not_configured_for_assets_without_profile(isolated_db, client, monkeypatch):
    monkeypatch.delenv("SNMP_TARGET_ASSET_ID", raising=False)
    await _seed(isolated_db, ip_address="10.0.9.21")
    await _seed(isolated_db, ip_address="10.0.9.22")

    response = await client.get("/api/monitoring")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["not_configured"] == 2
    assert body["polled"] == 0
    assert all(r["status"] == "not_configured" for r in body["results"])
    assert all(r["system"] is None and r["interfaces"] == [] for r in body["results"])


@pytest.mark.anyio
async def test_monitoring_polls_asset_with_resolved_profile(isolated_db, client, monkeypatch):
    asset = await _seed(isolated_db, ip_address="10.0.9.23")
    monkeypatch.setenv("SNMP_TARGET_ASSET_ID", str(asset["id"]))
    monkeypatch.setenv("SNMP_TARGET_COMMUNITY_REF", "SNMP_V2C_COMMUNITY")

    fake_result = SNMPPollResult(asset_id=asset["id"], polled_at=_now(), status="success")
    with patch(
        "app.snmp.client.SNMPClient.poll_asset", AsyncMock(return_value=fake_result)
    ) as mock_poll:
        response = await client.get("/api/monitoring")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["polled"] == 1
    assert body["results"][0]["status"] == "success"
    mock_poll.assert_called_once()


@pytest.mark.anyio
async def test_monitoring_returns_503_when_database_unreachable(client):
    with patch(
        "app.routes.monitoring.get_connection",
        AsyncMock(side_effect=OSError("connection refused")),
    ):
        response = await client.get("/api/monitoring")

    assert response.status_code == 503
    assert response.json()["detail"] == {"database": "unreachable"}


@pytest.mark.anyio
async def test_monitoring_never_leaks_community_secret(isolated_db, client, monkeypatch):
    # Gerçek ağa hiçbir SNMP paketi gönderilmez — `SNMPClient.poll_asset`
    # mock'lanıyor; burada yalnızca HTTP response'unun secret DEĞERİNİ
    # hiçbir koşulda taşımadığı doğrulanıyor.
    asset = await _seed(isolated_db, ip_address="10.0.9.24")
    monkeypatch.setenv("SNMP_TARGET_ASSET_ID", str(asset["id"]))
    monkeypatch.setenv("SNMP_TARGET_COMMUNITY_REF", "SNMP_MONITORING_LEAK_CHECK")
    monkeypatch.setenv("SNMP_MONITORING_LEAK_CHECK", "gizli-deger-monitoring-response-da-olmamali")

    fake_result = SNMPPollResult(asset_id=asset["id"], polled_at=_now(), status="success")
    with patch("app.snmp.client.SNMPClient.poll_asset", AsyncMock(return_value=fake_result)):
        response = await client.get("/api/monitoring")

    assert response.status_code == 200
    assert "gizli-deger-monitoring-response-da-olmamali" not in response.text
