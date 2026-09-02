"""`persist_scan_result` (discovery -> asset repository köprüsü) için
gerçek PostgreSQL'e bağlı testler. Hiçbir gerçek ağ taraması yapılmaz —
elle kurulan `ScanResult` nesneleri doğrudan `persist_scan_result`'a
verilir. `persist_scan_result` kendi bağlantısını kendi açıp kapattığı
için (gerçek kullanımdaki gibi), bu testler `tests/db/conftest.py`'deki
paylaşımlı rollback-tabanlı `db_conn` fixture'ını KULLANMAZ; bunun yerine
kendi test aralığını (`10.0.7.0/24`) her testten önce/sonra açıkça
temizler."""

import pytest

from app.db.assets import ensure_schema, get_asset_by_ip, get_connection
from app.discovery.schemas import PingResult, PortResult, ScanResult
from app.routes.discovery import persist_scan_result

_TEST_CIDR = "10.0.7.0/24"


async def _delete_test_range() -> None:
    conn = await get_connection()
    try:
        await ensure_schema(conn)
        await conn.execute(
            "DELETE FROM assets WHERE ip_address << $1::cidr", _TEST_CIDR
        )
    finally:
        await conn.close()


@pytest.fixture(autouse=True)
async def _clean_test_range():
    try:
        await _delete_test_range()
    except OSError:
        pytest.skip(
            "PostgreSQL erişilemiyor — önce "
            "`docker compose -f infra/docker-compose.yml up -d` çalıştırın"
        )
        return
    yield
    await _delete_test_range()


def _up_host(ip: str, **overrides) -> PingResult:
    defaults = dict(
        ip=ip,
        status="up",
        latency_ms=3.5,
        mac_address="AA-11-BB-22-CC-33",
        vendor="Dell Inc.",
        hostname="host.example.local",
        open_ports=[PortResult(port=443, status="open", latency_ms=1.1)],
        device_type="server",
        confidence="medium",
        evidence=["port: 443"],
    )
    defaults.update(overrides)
    return PingResult(**defaults)


@pytest.mark.anyio
async def test_persist_scan_result_creates_asset_for_up_host():
    ip = "10.0.7.1"
    scan_result = ScanResult(
        cidr=_TEST_CIDR, total_hosts=254, alive_hosts=1, hosts=[_up_host(ip)]
    )

    await persist_scan_result(scan_result)

    conn = await get_connection()
    try:
        asset = await get_asset_by_ip(conn, ip)
    finally:
        await conn.close()

    assert asset is not None
    assert str(asset["ip_address"]) == ip
    assert asset["hostname"] == "host.example.local"
    assert asset["mac_address"] == "AA-11-BB-22-CC-33"
    assert asset["vendor"] == "Dell Inc."
    assert asset["device_type"] == "server"
    assert asset["confidence"] == "medium"
    assert asset["evidence"] == ["port: 443"]
    assert asset["open_ports"] == [{"port": 443, "status": "open", "latency_ms": 1.1}]
    assert asset["status"] == "up"
    assert asset["latency_ms"] == 3.5


@pytest.mark.anyio
async def test_persist_scan_result_down_host_is_not_persisted():
    ip = "10.0.7.2"
    down_host = PingResult(ip=ip, status="down", latency_ms=None)
    scan_result = ScanResult(
        cidr=_TEST_CIDR, total_hosts=254, alive_hosts=0, hosts=[down_host]
    )

    await persist_scan_result(scan_result)

    conn = await get_connection()
    try:
        asset = await get_asset_by_ip(conn, ip)
    finally:
        await conn.close()

    assert asset is None


@pytest.mark.anyio
async def test_persist_scan_result_same_ip_twice_does_not_duplicate():
    ip = "10.0.7.3"
    first_scan = ScanResult(
        cidr=_TEST_CIDR, total_hosts=254, alive_hosts=1, hosts=[_up_host(ip)]
    )
    second_scan = ScanResult(
        cidr=_TEST_CIDR, total_hosts=254, alive_hosts=1, hosts=[_up_host(ip)]
    )

    await persist_scan_result(first_scan)
    await persist_scan_result(second_scan)

    conn = await get_connection()
    try:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM assets WHERE ip_address = $1::inet", ip
        )
    finally:
        await conn.close()

    assert count == 1


@pytest.mark.anyio
async def test_persist_scan_result_updates_last_seen_on_rescan():
    ip = "10.0.7.4"

    await persist_scan_result(
        ScanResult(
            cidr=_TEST_CIDR, total_hosts=254, alive_hosts=1, hosts=[_up_host(ip)]
        )
    )
    conn = await get_connection()
    try:
        first = await get_asset_by_ip(conn, ip)
    finally:
        await conn.close()

    await persist_scan_result(
        ScanResult(
            cidr=_TEST_CIDR, total_hosts=254, alive_hosts=1, hosts=[_up_host(ip)]
        )
    )
    conn = await get_connection()
    try:
        second = await get_asset_by_ip(conn, ip)
    finally:
        await conn.close()

    assert second["last_seen"] > first["last_seen"]
    assert second["updated_at"] > first["updated_at"]


@pytest.mark.anyio
async def test_persist_scan_result_isolates_per_host_failure():
    ok_ip_a = "10.0.7.5"
    ok_ip_b = "10.0.7.6"
    broken_host = PingResult(ip="not-an-ip-address", status="up", latency_ms=1.0)
    scan_result = ScanResult(
        cidr=_TEST_CIDR,
        total_hosts=254,
        alive_hosts=3,
        hosts=[_up_host(ok_ip_a), broken_host, _up_host(ok_ip_b)],
    )

    await persist_scan_result(scan_result)

    conn = await get_connection()
    try:
        asset_a = await get_asset_by_ip(conn, ok_ip_a)
        asset_b = await get_asset_by_ip(conn, ok_ip_b)
    finally:
        await conn.close()

    assert asset_a is not None
    assert asset_b is not None
