"""`GET /api/assets` için gerçek PostgreSQL'e bağlı testler.

Bu endpoint henüz filtreleme/pagination olmadan tüm `assets` tablosunu
okuduğu için testler tabloyu her test öncesi tamamen boşaltır
(`TRUNCATE ... CASCADE` — `agents.asset_id` artık `assets`'e FK ile
referans veriyor, bkz. Faz 28, bu yüzden düz `TRUNCATE` PostgreSQL
tarafından reddediliyor) — ama artık kök `conftest.py::isolated_db`
fixture'ı sayesinde bu, testin sonunda ROLLBACK edilen bir transaction
içinde çalışıyor: gerçek/kalıcı (commit edilmiş) veriye hiçbir etkisi
yok."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.db.assets import upsert_asset


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
async def _clean_assets_table(isolated_db):
    await isolated_db.execute("TRUNCATE TABLE assets CASCADE")


async def _seed(isolated_db, **overrides) -> dict:
    defaults = dict(
        ip_address="10.0.8.10",
        hostname="server.example.local",
        mac_address="AA-BB-CC-DD-EE-FF",
        vendor="Dell Inc.",
        device_type="server",
        confidence="medium",
        status="up",
        open_ports=[{"port": 443, "status": "open", "latency_ms": 1.5}],
        evidence=["port: 443"],
        last_seen=_now(),
        latency_ms=2.5,
    )
    defaults.update(overrides)
    return await upsert_asset(isolated_db, **defaults)


@pytest.mark.anyio
async def test_get_assets_returns_empty_list_when_database_is_empty(client):
    response = await client.get("/api/assets")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_get_assets_returns_single_asset_with_all_fields(isolated_db, client):
    await _seed(isolated_db)

    response = await client.get("/api/assets")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    asset = body[0]
    assert asset["ip_address"] == "10.0.8.10"
    assert asset["hostname"] == "server.example.local"
    assert asset["mac_address"] == "AA-BB-CC-DD-EE-FF"
    assert asset["vendor"] == "Dell Inc."
    assert asset["device_type"] == "server"
    assert asset["confidence"] == "medium"
    assert asset["status"] == "up"
    assert asset["latency_ms"] == 2.5
    assert asset["evidence"] == ["port: 443"]
    assert asset["open_ports"] == [
        {"port": 443, "status": "open", "latency_ms": 1.5}
    ]
    for key in ("id", "last_seen", "created_at", "updated_at"):
        assert key in asset and asset[key] is not None


@pytest.mark.anyio
async def test_get_assets_returns_multiple_assets(isolated_db, client):
    await _seed(isolated_db, ip_address="10.0.8.11", hostname="a")
    await _seed(isolated_db, ip_address="10.0.8.12", hostname="b")
    await _seed(isolated_db, ip_address="10.0.8.13", hostname="c")

    response = await client.get("/api/assets")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    assert {a["ip_address"] for a in body} == {
        "10.0.8.11",
        "10.0.8.12",
        "10.0.8.13",
    }


@pytest.mark.anyio
async def test_get_assets_orders_by_last_seen_desc(isolated_db, client):
    now = _now()
    await _seed(isolated_db, ip_address="10.0.8.21", last_seen=now - timedelta(hours=2))
    await _seed(isolated_db, ip_address="10.0.8.22", last_seen=now)
    await _seed(isolated_db, ip_address="10.0.8.23", last_seen=now - timedelta(hours=1))

    response = await client.get("/api/assets")

    ips_in_order = [a["ip_address"] for a in response.json()]
    assert ips_in_order == ["10.0.8.22", "10.0.8.23", "10.0.8.21"]


@pytest.mark.anyio
async def test_get_assets_serializes_null_fields_as_null(isolated_db, client):
    await _seed(
        isolated_db,
        ip_address="10.0.8.30",
        hostname=None,
        mac_address=None,
        vendor=None,
        latency_ms=None,
    )

    response = await client.get("/api/assets")

    asset = response.json()[0]
    assert asset["hostname"] is None
    assert asset["mac_address"] is None
    assert asset["vendor"] is None
    assert asset["latency_ms"] is None


@pytest.mark.anyio
async def test_get_assets_serializes_open_ports(isolated_db, client):
    ports = [
        {"port": 22, "status": "open", "latency_ms": 1.1},
        {"port": 443, "status": "open", "latency_ms": None},
    ]
    await _seed(isolated_db, ip_address="10.0.8.40", open_ports=ports)

    response = await client.get("/api/assets")

    assert response.json()[0]["open_ports"] == ports


@pytest.mark.anyio
async def test_get_assets_serializes_evidence(isolated_db, client):
    evidence = ["vendor: Fortinet", "port: 443 open"]
    await _seed(isolated_db, ip_address="10.0.8.41", evidence=evidence)

    response = await client.get("/api/assets")

    assert response.json()[0]["evidence"] == evidence


@pytest.mark.anyio
async def test_get_assets_returns_503_when_database_unreachable(client):
    """Gerçek sunucuyu durdurmadan "erişilemez" durumunu üretmek için
    yalnızca bağlantı adımı mock'lanır — sorgu/serileştirme mantığı
    gerçek kalır. Diğer tüm testler gerçek, canlı PostgreSQL kullanır."""
    with patch(
        "app.routes.assets.get_connection",
        AsyncMock(side_effect=OSError("connection refused")),
    ):
        response = await client.get("/api/assets")

    assert response.status_code == 503
    assert response.json()["detail"] == {"database": "unreachable"}


@pytest.mark.anyio
async def test_get_assets_response_matches_expected_schema_shape(isolated_db, client):
    await _seed(isolated_db)

    response = await client.get("/api/assets")

    asset = response.json()[0]
    expected_keys = {
        "id",
        "ip_address",
        "hostname",
        "mac_address",
        "vendor",
        "device_type",
        "confidence",
        "evidence",
        "open_ports",
        "status",
        "latency_ms",
        "last_seen",
        "created_at",
        "updated_at",
    }
    assert set(asset.keys()) == expected_keys


@pytest.mark.anyio
async def test_existing_discovery_endpoint_still_works(client):
    """Regresyon kontrolü: /api/assets eklenmesi discovery endpoint'ini
    bozmamalı."""
    response = await client.post("/api/discovery/icmp", json={"cidr": "not-a-cidr"})

    assert response.status_code == 400
