import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.discovery.cidr import InvalidCIDRError
from app.discovery.schemas import PingResult, PortResult
from app.discovery.scanner import scan_network


@pytest.mark.anyio
async def test_scan_network_returns_correct_totals_and_hosts():
    async def fake_ping_host(ip: str, timeout_ms: int) -> PingResult:
        if ip == "10.0.5.1":
            return PingResult(ip=ip, status="up", latency_ms=2.1)
        return PingResult(ip=ip, status="down", latency_ms=None)

    get_mac_address_mock = AsyncMock(return_value="00-09-0F-09-00-08")
    lookup_vendor_mock = MagicMock(return_value="Fortinet, Inc.")
    get_hostname_mock = AsyncMock(return_value="firewall.example.local")
    scan_ports_mock = AsyncMock(
        return_value=[PortResult(port=443, status="open", latency_ms=2.4)]
    )

    with (
        patch(
            "app.discovery.scanner.ping_host", AsyncMock(side_effect=fake_ping_host)
        ),
        patch("app.discovery.scanner.get_mac_address", get_mac_address_mock),
        patch("app.discovery.scanner.lookup_vendor", lookup_vendor_mock),
        patch("app.discovery.scanner.get_hostname", get_hostname_mock),
        patch("app.discovery.scanner.scan_ports", scan_ports_mock),
    ):
        result = await scan_network("10.0.5.0/30")

    assert result.cidr == "10.0.5.0/30"
    assert result.total_hosts == 2
    assert result.alive_hosts == 1
    assert [h.ip for h in result.hosts] == ["10.0.5.1", "10.0.5.2"]
    assert result.hosts[0].status == "up"
    assert result.hosts[0].mac_address == "00-09-0F-09-00-08"
    assert result.hosts[0].vendor == "Fortinet, Inc."
    assert result.hosts[0].hostname == "firewall.example.local"
    assert result.hosts[0].open_ports == [
        PortResult(port=443, status="open", latency_ms=2.4)
    ]
    # classify_device gerçek (mocklanmamış) çalışır: Fortinet vendor'ı
    # tier-1 kuralıyla eşleşir.
    assert result.hosts[0].device_type == "firewall"
    assert result.hosts[0].confidence == "high"
    assert result.hosts[0].evidence == ["vendor: Fortinet"]
    assert result.hosts[1].status == "down"
    assert result.hosts[1].mac_address is None
    assert result.hosts[1].vendor is None
    assert result.hosts[1].hostname is None
    assert result.hosts[1].open_ports == []
    assert result.hosts[1].device_type == "unknown"
    assert result.hosts[1].confidence == "low"
    assert result.hosts[1].evidence == []
    get_mac_address_mock.assert_called_once_with("10.0.5.1")
    lookup_vendor_mock.assert_called_once_with("00-09-0F-09-00-08")
    get_hostname_mock.assert_called_once_with("10.0.5.1")
    scan_ports_mock.assert_called_once()


@pytest.mark.anyio
async def test_scan_network_sets_vendor_none_when_mac_has_no_known_vendor():
    async def fake_ping_host(ip: str, timeout_ms: int) -> PingResult:
        return PingResult(ip=ip, status="up", latency_ms=1.0)

    lookup_vendor_mock = MagicMock(return_value=None)

    with (
        patch(
            "app.discovery.scanner.ping_host", AsyncMock(side_effect=fake_ping_host)
        ),
        patch(
            "app.discovery.scanner.get_mac_address",
            AsyncMock(return_value="FF-FF-FF-00-00-00"),
        ),
        patch("app.discovery.scanner.lookup_vendor", lookup_vendor_mock),
        patch("app.discovery.scanner.get_hostname", AsyncMock(return_value=None)),
        patch("app.discovery.scanner.scan_ports", AsyncMock(return_value=[])),
    ):
        result = await scan_network("10.0.5.0/30")

    assert result.hosts[0].mac_address == "FF-FF-FF-00-00-00"
    assert result.hosts[0].vendor is None


@pytest.mark.anyio
async def test_scan_network_skips_vendor_lookup_when_mac_not_found():
    async def fake_ping_host(ip: str, timeout_ms: int) -> PingResult:
        return PingResult(ip=ip, status="up", latency_ms=1.0)

    lookup_vendor_mock = MagicMock(return_value="Should not be called")

    with (
        patch(
            "app.discovery.scanner.ping_host", AsyncMock(side_effect=fake_ping_host)
        ),
        patch("app.discovery.scanner.get_mac_address", AsyncMock(return_value=None)),
        patch("app.discovery.scanner.lookup_vendor", lookup_vendor_mock),
        patch(
            "app.discovery.scanner.get_hostname",
            AsyncMock(return_value="SHOULD-NOT-MATTER"),
        ),
        patch("app.discovery.scanner.scan_ports", AsyncMock(return_value=[])),
    ):
        result = await scan_network("10.0.5.0/30")

    assert result.hosts[0].mac_address is None
    assert result.hosts[0].vendor is None
    lookup_vendor_mock.assert_not_called()


@pytest.mark.anyio
async def test_scan_network_skips_hostname_lookup_for_down_hosts():
    async def fake_ping_host(ip: str, timeout_ms: int) -> PingResult:
        return PingResult(ip=ip, status="down", latency_ms=None)

    get_hostname_mock = AsyncMock(return_value="SHOULD-NOT-BE-CALLED")

    with (
        patch(
            "app.discovery.scanner.ping_host", AsyncMock(side_effect=fake_ping_host)
        ),
        patch("app.discovery.scanner.get_hostname", get_hostname_mock),
    ):
        result = await scan_network("10.0.5.0/30")

    assert all(h.hostname is None for h in result.hosts)
    get_hostname_mock.assert_not_called()


@pytest.mark.anyio
async def test_scan_network_continues_when_one_hostname_lookup_fails():
    async def fake_ping_host(ip: str, timeout_ms: int) -> PingResult:
        return PingResult(ip=ip, status="up", latency_ms=1.0)

    async def fake_get_hostname(ip: str) -> str | None:
        if ip == "10.0.5.1":
            return None  # DNS çözülemedi
        return "server02.example.local"

    with (
        patch(
            "app.discovery.scanner.ping_host", AsyncMock(side_effect=fake_ping_host)
        ),
        patch("app.discovery.scanner.get_mac_address", AsyncMock(return_value=None)),
        patch(
            "app.discovery.scanner.get_hostname",
            AsyncMock(side_effect=fake_get_hostname),
        ),
        patch("app.discovery.scanner.scan_ports", AsyncMock(return_value=[])),
    ):
        result = await scan_network("10.0.5.0/30")

    hosts_by_ip = {h.ip: h for h in result.hosts}
    assert hosts_by_ip["10.0.5.1"].hostname is None
    assert hosts_by_ip["10.0.5.1"].status == "up"
    assert hosts_by_ip["10.0.5.2"].hostname == "server02.example.local"


@pytest.mark.anyio
async def test_scan_network_skips_port_scan_for_down_hosts():
    async def fake_ping_host(ip: str, timeout_ms: int) -> PingResult:
        return PingResult(ip=ip, status="down", latency_ms=None)

    scan_ports_mock = AsyncMock(return_value=[])

    with (
        patch(
            "app.discovery.scanner.ping_host", AsyncMock(side_effect=fake_ping_host)
        ),
        patch("app.discovery.scanner.scan_ports", scan_ports_mock),
    ):
        result = await scan_network("10.0.5.0/30")

    assert all(h.open_ports == [] for h in result.hosts)
    scan_ports_mock.assert_not_called()


@pytest.mark.anyio
async def test_scan_network_continues_when_one_host_enrichment_fails():
    async def fake_ping_host(ip: str, timeout_ms: int) -> PingResult:
        return PingResult(ip=ip, status="up", latency_ms=1.0)

    async def fake_scan_ports(ip: str, ports, port_concurrency=None):
        if ip == "10.0.5.1":
            raise RuntimeError("beklenmeyen tarama hatası")
        return [PortResult(port=443, status="open", latency_ms=1.5)]

    with (
        patch(
            "app.discovery.scanner.ping_host", AsyncMock(side_effect=fake_ping_host)
        ),
        patch("app.discovery.scanner.get_mac_address", AsyncMock(return_value=None)),
        patch("app.discovery.scanner.get_hostname", AsyncMock(return_value=None)),
        patch(
            "app.discovery.scanner.scan_ports", AsyncMock(side_effect=fake_scan_ports)
        ),
    ):
        result = await scan_network("10.0.5.0/30")

    hosts_by_ip = {h.ip: h for h in result.hosts}
    # 10.0.5.1'in zenginleştirmesi patladı ama ping sonucu (up/latency)
    # korunuyor, tüm scan çökmüyor.
    assert hosts_by_ip["10.0.5.1"].status == "up"
    assert hosts_by_ip["10.0.5.1"].open_ports == []
    # Diğer host etkilenmeden tam sonucunu alıyor.
    assert hosts_by_ip["10.0.5.2"].open_ports == [
        PortResult(port=443, status="open", latency_ms=1.5)
    ]


@pytest.mark.anyio
async def test_scan_network_raises_for_invalid_cidr():
    with pytest.raises(InvalidCIDRError):
        await scan_network("not-a-cidr")


@pytest.mark.anyio
async def test_scan_network_limits_concurrency():
    active = 0
    max_active = 0

    async def fake_ping_host(ip: str, timeout_ms: int) -> PingResult:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return PingResult(ip=ip, status="down", latency_ms=None)

    with patch(
        "app.discovery.scanner.ping_host", AsyncMock(side_effect=fake_ping_host)
    ):
        await scan_network("10.0.5.0/24", concurrency=5)

    assert max_active == 5
