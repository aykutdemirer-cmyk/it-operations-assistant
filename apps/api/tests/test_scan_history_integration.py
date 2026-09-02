"""Discovery endpoint'inin scan-history entegrasyonu için gerçek
PostgreSQL'e bağlı testler. Gerçek `127.0.0.1/32` taraması kullanılır
(`scan_network` hiç mock'lanmaz) — bu, gerçekten çalışan discovery +
scan history + asset persistence uçtan uca zincirini doğrular.

`isolated_db` (bkz. kök `conftest.py`) sayesinde `TRUNCATE TABLE`
çağrıları testin sonunda ROLLBACK edilen bir transaction içinde
çalışıyor — gerçek/kalıcı veriye hiçbir etkisi yok."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
async def _clean_state(isolated_db):
    await isolated_db.execute("TRUNCATE TABLE assets CASCADE")
    await isolated_db.execute("TRUNCATE TABLE scans")


@pytest.mark.anyio
async def test_successful_scan_creates_completed_history_record(client):
    response = await client.post("/api/discovery/icmp", json={"cidr": "127.0.0.1/32"})

    assert response.status_code == 200

    scans = (await client.get("/api/scans")).json()
    assert len(scans) == 1
    scan = scans[0]
    assert scan["cidr"] == "127.0.0.1/32"
    assert scan["status"] == "completed"
    assert scan["hosts_scanned"] == 1
    assert scan["hosts_discovered"] == 1
    assert scan["duration_ms"] is not None
    assert scan["duration_ms"] >= 0
    assert scan["open_ports"] >= 0


@pytest.mark.anyio
async def test_invalid_cidr_returns_400_and_creates_failed_history_record(client):
    response = await client.post("/api/discovery/icmp", json={"cidr": "not-a-cidr"})

    # Mevcut davranis (400 + hata detayi) aynen korunuyor.
    assert response.status_code == 400
    assert "detail" in response.json()

    scans = (await client.get("/api/scans")).json()
    assert len(scans) == 1
    assert scans[0]["status"] == "failed"
    assert scans[0]["cidr"] == "not-a-cidr"


@pytest.mark.anyio
async def test_discovery_response_unaffected_when_history_db_unreachable(client):
    """Scan history için bağlantı kurulamazsa (OSError), discovery normal
    şekilde çalışmaya devam etmeli ve response'u hiç değişmemeli — asset
    persistence de (ayrı bir bağlantı kullandığı için) etkilenmemeli."""
    with patch(
        "app.routes.discovery.scans_repo.get_connection",
        AsyncMock(side_effect=OSError("connection refused")),
    ):
        response = await client.post("/api/discovery/icmp", json={"cidr": "127.0.0.1/32"})

    assert response.status_code == 200
    body = response.json()
    assert body["cidr"] == "127.0.0.1/32"
    assert body["alive_hosts"] == 1

    assets = (await client.get("/api/assets")).json()
    assert any(a["ip_address"] == "127.0.0.1" for a in assets)

    scans = (await client.get("/api/scans")).json()
    assert scans == []
