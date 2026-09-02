"""`GET /api/scans` için gerçek PostgreSQL'e bağlı testler.

`isolated_db` (bkz. kök `conftest.py`) sayesinde `TRUNCATE TABLE scans`
çalışsa bile gerçek/kalıcı veriye hiçbir etkisi yok — test transaction'ı
rollback ile bitiyor."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.db.scans import create_scan, complete_scan, fail_scan


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
async def _clean_scans_table(isolated_db):
    await isolated_db.execute("TRUNCATE TABLE scans")


@pytest.mark.anyio
async def test_get_scans_returns_empty_list_when_no_scans(client):
    response = await client.get("/api/scans")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_get_scans_returns_completed_scan_with_all_fields(isolated_db, client):
    started = _now()
    scan = await create_scan(isolated_db, cidr="10.0.9.0/24", started_at=started)
    await complete_scan(
        isolated_db,
        scan_id=scan["id"],
        completed_at=started + timedelta(seconds=1),
        duration_ms=1000.0,
        hosts_scanned=254,
        hosts_discovered=2,
        open_ports=5,
    )

    response = await client.get("/api/scans")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    scan_json = body[0]
    assert scan_json["cidr"] == "10.0.9.0/24"
    assert scan_json["status"] == "completed"
    assert scan_json["duration_ms"] == 1000.0
    assert scan_json["hosts_scanned"] == 254
    assert scan_json["hosts_discovered"] == 2
    assert scan_json["open_ports"] == 5
    assert scan_json["completed_at"] is not None
    assert "id" in scan_json
    assert "started_at" in scan_json


@pytest.mark.anyio
async def test_get_scans_returns_failed_scan(isolated_db, client):
    started = _now()
    scan = await create_scan(isolated_db, cidr="not-a-cidr", started_at=started)
    await fail_scan(
        isolated_db,
        scan_id=scan["id"],
        completed_at=started + timedelta(milliseconds=20),
        duration_ms=20.0,
    )

    response = await client.get("/api/scans")

    assert response.status_code == 200
    assert response.json()[0]["status"] == "failed"


@pytest.mark.anyio
async def test_get_scans_orders_by_started_at_desc(isolated_db, client):
    now = _now()
    await create_scan(isolated_db, cidr="10.0.9.1/32", started_at=now - timedelta(hours=2))
    await create_scan(isolated_db, cidr="10.0.9.2/32", started_at=now)
    await create_scan(isolated_db, cidr="10.0.9.3/32", started_at=now - timedelta(hours=1))

    response = await client.get("/api/scans")

    cidrs_in_order = [s["cidr"] for s in response.json()]
    assert cidrs_in_order == ["10.0.9.2/32", "10.0.9.3/32", "10.0.9.1/32"]


@pytest.mark.anyio
async def test_get_scans_returns_503_when_database_unreachable(client):
    with patch(
        "app.routes.scans.get_connection",
        AsyncMock(side_effect=OSError("connection refused")),
    ):
        response = await client.get("/api/scans")

    assert response.status_code == 503
    assert response.json()["detail"] == {"database": "unreachable"}


@pytest.mark.anyio
async def test_get_scans_response_matches_expected_schema_shape(isolated_db, client):
    await create_scan(isolated_db, cidr="10.0.9.9/32", started_at=_now())

    response = await client.get("/api/scans")

    scan_json = response.json()[0]
    expected_keys = {
        "id",
        "cidr",
        "started_at",
        "completed_at",
        "duration_ms",
        "hosts_scanned",
        "hosts_discovered",
        "open_ports",
        "status",
    }
    assert set(scan_json.keys()) == expected_keys
