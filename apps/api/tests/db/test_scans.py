"""`scans` repository katmanı için gerçek PostgreSQL'e bağlı testler.

Mevcut `db_conn` fixture'ı (bkz. `conftest.py`) kullanılıyor — o fixture
`app.db.assets.ensure_schema`'yı çağırıyor, ama bu aynı `init.sql`
dosyasını çalıştırdığı için `scans` tablosunu da garanti ediyor; ayrı bir
fixture'a gerek yok."""

from datetime import datetime, timedelta, timezone

import pytest

from app.db.scans import complete_scan, create_scan, fail_scan, list_scans


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.anyio
async def test_create_scan_starts_in_running_status(db_conn):
    started = _now()
    scan = await create_scan(db_conn, cidr="10.0.9.0/24", started_at=started)

    assert scan["cidr"] == "10.0.9.0/24"
    assert scan["status"] == "running"
    assert scan["completed_at"] is None
    assert scan["duration_ms"] is None
    assert scan["hosts_scanned"] == 0
    assert scan["hosts_discovered"] == 0
    assert scan["open_ports"] == 0


@pytest.mark.anyio
async def test_complete_scan_sets_stats_and_status(db_conn):
    started = _now()
    scan = await create_scan(db_conn, cidr="10.0.9.0/24", started_at=started)
    completed = started + timedelta(seconds=2)

    result = await complete_scan(
        db_conn,
        scan_id=scan["id"],
        completed_at=completed,
        duration_ms=2000.0,
        hosts_scanned=254,
        hosts_discovered=3,
        open_ports=7,
    )

    assert result["status"] == "completed"
    assert result["completed_at"] == completed
    assert result["duration_ms"] == 2000.0
    assert result["hosts_scanned"] == 254
    assert result["hosts_discovered"] == 3
    assert result["open_ports"] == 7


@pytest.mark.anyio
async def test_fail_scan_sets_failed_status(db_conn):
    started = _now()
    scan = await create_scan(db_conn, cidr="not-a-cidr", started_at=started)
    completed = started + timedelta(milliseconds=50)

    result = await fail_scan(
        db_conn, scan_id=scan["id"], completed_at=completed, duration_ms=50.0
    )

    assert result["status"] == "failed"
    assert result["completed_at"] == completed
    assert result["duration_ms"] == 50.0
    # basarisiz taramada istatistikler bilinmez, varsayilan 0'da kalir
    assert result["hosts_scanned"] == 0
    assert result["hosts_discovered"] == 0
    assert result["open_ports"] == 0


@pytest.mark.anyio
async def test_list_scans_orders_by_started_at_desc(db_conn):
    now = _now()
    older = await create_scan(db_conn, cidr="10.0.9.1/32", started_at=now - timedelta(hours=1))
    newer = await create_scan(db_conn, cidr="10.0.9.2/32", started_at=now)

    scans = await list_scans(db_conn)
    ids_in_order = [s["id"] for s in scans]

    assert ids_in_order.index(newer["id"]) < ids_in_order.index(older["id"])


@pytest.mark.anyio
async def test_list_scans_returns_empty_list_when_no_scans(db_conn):
    # `db_conn`'ün transaction'ı rollback ile bittiği için burada
    # TRUNCATE etmek kalıcı veriyi bozmaz (bkz. `conftest.py`) — ama
    # bu test, gerçek geliştirme sırasında (örn. tarayıcıda manuel
    # taramalar) tabloya eklenmiş, bu transaction başlamadan önce
    # COMMIT edilmiş satırları göz ardı etmeden "boş" durumunu test
    # edemez. Diğer testlerden farklı olarak açıkça izole ediliyor.
    await db_conn.execute("TRUNCATE TABLE scans")

    scans = await list_scans(db_conn)
    assert scans == []
