"""`assets` repository katmanı için gerçek PostgreSQL'e bağlı testler.

Bu testler kasıtlı olarak gerçek bir veritabanı bağlantısı gerektirir —
mock database ile repository'nin doğru çalıştığı kanıtlanamaz (INET/JSONB
tip dönüşümleri, UNIQUE constraint, ON CONFLICT davranışı gibi gerçek
PostgreSQL semantiğine bağlıdır). PostgreSQL erişilemezse `db_conn`
fixture'ı testi açık bir nedenle skip eder (bkz. `conftest.py`)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest

from app.db.assets import (
    ensure_schema,
    get_asset_by_id,
    get_asset_by_ip,
    get_connection,
    upsert_asset,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.anyio
async def test_insert_new_asset(db_conn):
    result = await upsert_asset(
        db_conn,
        ip_address="10.0.5.101",
        hostname="server01.example.local",
        mac_address="AA-BB-CC-DD-EE-01",
        vendor="Dell Inc.",
        device_type="server",
        confidence="medium",
        status="up",
        open_ports=[{"port": 443, "status": "open", "latency_ms": 1.2}],
        evidence=["port: 443"],
        last_seen=_now(),
    )

    assert str(result["ip_address"]) == "10.0.5.101"
    assert result["hostname"] == "server01.example.local"
    assert result["status"] == "up"
    assert result["created_at"] is not None
    assert result["updated_at"] is not None


@pytest.mark.anyio
async def test_upsert_same_ip_does_not_create_duplicate(db_conn):
    ip = "10.0.5.102"
    await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname="a",
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )
    await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname="a",
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )

    count = await db_conn.fetchval(
        "SELECT COUNT(*) FROM assets WHERE ip_address = $1::inet", ip
    )
    assert count == 1


@pytest.mark.anyio
async def test_upsert_does_not_change_created_at(db_conn):
    ip = "10.0.5.103"
    first = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )
    second = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )

    assert first["created_at"] == second["created_at"]


@pytest.mark.anyio
async def test_upsert_changes_updated_at(db_conn):
    ip = "10.0.5.104"
    first = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )
    second = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now() + timedelta(seconds=1),
    )

    assert second["updated_at"] > first["updated_at"]


@pytest.mark.anyio
async def test_upsert_updates_last_seen(db_conn):
    ip = "10.0.5.105"
    first_seen = _now() - timedelta(hours=1)
    second_seen = _now()

    await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=first_seen,
    )
    result = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=second_seen,
    )

    assert result["last_seen"] == second_seen


@pytest.mark.anyio
async def test_upsert_updates_hostname_when_provided(db_conn):
    ip = "10.0.5.106"
    await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname="old-name",
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )
    result = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname="new-name",
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )

    assert result["hostname"] == "new-name"


@pytest.mark.anyio
async def test_upsert_preserves_hostname_when_new_value_is_null(db_conn):
    ip = "10.0.5.107"
    await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname="firewall.company.local",
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )

    # İkinci taramada DNS çözülemedi (hostname=None) — mevcut değer
    # gereksiz yere silinmemeli.
    result = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )

    assert result["hostname"] == "firewall.company.local"


@pytest.mark.anyio
async def test_upsert_updates_mac_address(db_conn):
    ip = "10.0.5.108"
    await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address="AA-AA-AA-AA-AA-AA",
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )
    result = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address="BB-BB-BB-BB-BB-BB",
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )

    assert result["mac_address"] == "BB-BB-BB-BB-BB-BB"


@pytest.mark.anyio
async def test_upsert_preserves_mac_address_when_new_value_is_null(db_conn):
    ip = "10.0.5.109"
    await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address="AA-AA-AA-AA-AA-AA",
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )
    result = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )

    assert result["mac_address"] == "AA-AA-AA-AA-AA-AA"


@pytest.mark.anyio
async def test_upsert_updates_vendor(db_conn):
    ip = "10.0.5.110"
    await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor="Old Vendor",
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )
    result = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor="Fortinet, Inc.",
        device_type="firewall",
        confidence="high",
        status="up",
        open_ports=[],
        evidence=["vendor: Fortinet"],
        last_seen=_now(),
    )

    assert result["vendor"] == "Fortinet, Inc."


@pytest.mark.anyio
async def test_upsert_preserves_vendor_when_new_value_is_null(db_conn):
    ip = "10.0.5.111"
    await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor="Fortinet, Inc.",
        device_type="firewall",
        confidence="high",
        status="up",
        open_ports=[],
        evidence=["vendor: Fortinet"],
        last_seen=_now(),
    )
    result = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )

    assert result["vendor"] == "Fortinet, Inc."


@pytest.mark.anyio
async def test_upsert_updates_device_type(db_conn):
    ip = "10.0.5.112"
    await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )
    result = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor="Fortinet, Inc.",
        device_type="firewall",
        confidence="high",
        status="up",
        open_ports=[],
        evidence=["vendor: Fortinet"],
        last_seen=_now(),
    )

    assert result["device_type"] == "firewall"
    assert result["confidence"] == "high"


@pytest.mark.anyio
async def test_open_ports_jsonb_roundtrip(db_conn):
    ip = "10.0.5.113"
    ports = [
        {"port": 22, "status": "open", "latency_ms": 2.1},
        {"port": 443, "status": "open", "latency_ms": 2.4},
    ]

    result = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=ports,
        evidence=[],
        last_seen=_now(),
    )

    assert result["open_ports"] == ports


@pytest.mark.anyio
async def test_evidence_jsonb_roundtrip(db_conn):
    ip = "10.0.5.114"
    evidence = ["vendor: Fortinet"]

    result = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor="Fortinet, Inc.",
        device_type="firewall",
        confidence="high",
        status="up",
        open_ports=[],
        evidence=evidence,
        last_seen=_now(),
    )

    assert result["evidence"] == evidence


@pytest.mark.anyio
async def test_ip_address_stored_as_inet(db_conn):
    ip = "10.0.5.115"
    await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )

    column_type = await db_conn.fetchval(
        """
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'assets' AND column_name = 'ip_address'
        """
    )
    assert column_type == "inet"

    fetched = await get_asset_by_ip(db_conn, ip)
    assert str(fetched["ip_address"]) == ip


@pytest.mark.anyio
async def test_get_asset_by_id_returns_matching_row(db_conn):
    inserted = await upsert_asset(
        db_conn,
        ip_address="10.0.5.116",
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )

    fetched = await get_asset_by_id(db_conn, inserted["id"])
    assert fetched is not None
    assert fetched["id"] == inserted["id"]
    assert str(fetched["ip_address"]) == "10.0.5.116"


@pytest.mark.anyio
async def test_get_asset_by_id_returns_none_when_missing(db_conn):
    fetched = await get_asset_by_id(db_conn, uuid4())
    assert fetched is None


@pytest.mark.anyio
async def test_multiple_distinct_assets_coexist(db_conn):
    ip_a, ip_b = "10.0.5.116", "10.0.5.117"

    await upsert_asset(
        db_conn,
        ip_address=ip_a,
        hostname="host-a",
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )
    await upsert_asset(
        db_conn,
        ip_address=ip_b,
        hostname="host-b",
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )

    asset_a = await get_asset_by_ip(db_conn, ip_a)
    asset_b = await get_asset_by_ip(db_conn, ip_b)

    assert asset_a["hostname"] == "host-a"
    assert asset_b["hostname"] == "host-b"


@pytest.mark.anyio
async def test_invalid_ip_address_raises_error(db_conn):
    with pytest.raises(asyncpg.PostgresError):
        await upsert_asset(
            db_conn,
            ip_address="not-an-ip-address",
            hostname=None,
            mac_address=None,
            vendor=None,
            device_type="unknown",
            confidence="low",
            status="up",
            open_ports=[],
            evidence=[],
            last_seen=_now(),
        )


@pytest.mark.anyio
async def test_upsert_updates_status(db_conn):
    ip = "10.0.5.120"
    await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )
    # status bir gozlem alanidir (kimlik alani degil): yeni tarama
    # "down" bulduysa, eski "up" degeri korunmamali.
    result = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="down",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )

    assert result["status"] == "down"


@pytest.mark.anyio
async def test_upsert_updates_open_ports(db_conn):
    ip = "10.0.5.121"
    await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[{"port": 22, "status": "open", "latency_ms": 1.0}],
        evidence=[],
        last_seen=_now(),
    )
    new_ports = [{"port": 443, "status": "open", "latency_ms": 2.0}]
    result = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=new_ports,
        evidence=[],
        last_seen=_now(),
    )

    assert result["open_ports"] == new_ports


@pytest.mark.anyio
async def test_upsert_updates_evidence(db_conn):
    ip = "10.0.5.122"
    await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=["port: 22"],
        last_seen=_now(),
    )
    new_evidence = ["vendor: Fortinet", "port: 443"]
    result = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor="Fortinet, Inc.",
        device_type="firewall",
        confidence="high",
        status="up",
        open_ports=[],
        evidence=new_evidence,
        last_seen=_now(),
    )

    assert result["evidence"] == new_evidence


@pytest.mark.anyio
async def test_upsert_updates_latency_ms(db_conn):
    ip = "10.0.5.123"
    await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
        latency_ms=5.0,
    )
    result = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
        latency_ms=12.3,
    )

    assert result["latency_ms"] == 12.3


@pytest.mark.anyio
async def test_upsert_overwrites_latency_ms_with_null_when_host_goes_down(db_conn):
    ip = "10.0.5.124"
    await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
        latency_ms=5.0,
    )
    # latency_ms bir gozlem alanidir (hostname/mac/vendor gibi bir
    # kimlik alani degil): host artik "down" ise eski "up" iken
    # olculmus gecikme degeri korunmamali, aksi halde yanlis bilgi
    # verir (bkz. upsert_asset docstring).
    result = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=None,
        mac_address=None,
        vendor=None,
        device_type="unknown",
        confidence="low",
        status="down",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
        latency_ms=None,
    )

    assert result["latency_ms"] is None
    assert result["status"] == "down"


@pytest.mark.anyio
async def test_sql_injection_like_string_is_stored_as_literal_text(db_conn):
    ip = "10.0.5.125"
    malicious = "'; DROP TABLE assets; --"

    result = await upsert_asset(
        db_conn,
        ip_address=ip,
        hostname=malicious,
        mac_address=None,
        vendor=malicious,
        device_type="unknown",
        confidence="low",
        status="up",
        open_ports=[],
        evidence=[malicious],
        last_seen=_now(),
    )

    assert result["hostname"] == malicious
    assert result["vendor"] == malicious
    assert result["evidence"] == [malicious]

    # Parameterized query kullanildigi icin tablo bozulmadan calismaya
    # devam ediyor olmali.
    count = await db_conn.fetchval("SELECT COUNT(*) FROM assets")
    assert count >= 1


@pytest.mark.anyio
async def test_transaction_rollback_discards_upsert():
    """`upsert_asset`, kendi transaction yonetimini yapmaz — cagiranin
    transaction'ina katilir. Bu test, diger testlerin kullandigi
    paylasilan `db_conn` fixture'ini (kendisi zaten bir rollback'e
    sarili) degil, kendi bagimsiz baglantisini/transaction'ini kurar ki
    rollback sinirini gercekten test edebilsin."""
    ip = "10.0.9.199"

    conn = await get_connection()
    try:
        await ensure_schema(conn)
        tx = conn.transaction()
        await tx.start()
        try:
            await upsert_asset(
                conn,
                ip_address=ip,
                hostname="should-not-persist",
                mac_address=None,
                vendor=None,
                device_type="unknown",
                confidence="low",
                status="up",
                open_ports=[],
                evidence=[],
                last_seen=_now(),
            )
        finally:
            await tx.rollback()
    finally:
        await conn.close()

    verify_conn = await get_connection()
    try:
        result = await get_asset_by_ip(verify_conn, ip)
        assert result is None
    finally:
        await verify_conn.close()
