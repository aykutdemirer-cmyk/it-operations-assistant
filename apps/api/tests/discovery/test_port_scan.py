import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.discovery.port_scan import COMMON_PORTS, scan_port, scan_ports


def _fake_open_connection(writer_close_side_effect=None):
    reader = MagicMock()
    writer = MagicMock()
    writer.close = MagicMock(side_effect=writer_close_side_effect)
    writer.wait_closed = AsyncMock()
    return AsyncMock(return_value=(reader, writer))


@pytest.mark.anyio
async def test_scan_port_returns_open_when_connection_succeeds():
    with patch(
        "app.discovery.port_scan.asyncio.open_connection",
        _fake_open_connection(),
    ):
        result = await scan_port("10.0.5.1", 443)

    assert result.port == 443
    assert result.status == "open"
    assert result.latency_ms is not None
    assert result.latency_ms >= 0


@pytest.mark.anyio
async def test_scan_port_returns_closed_on_connection_refused():
    with patch(
        "app.discovery.port_scan.asyncio.open_connection",
        AsyncMock(side_effect=ConnectionRefusedError()),
    ):
        result = await scan_port("10.0.5.1", 21)

    assert result.status == "closed"
    assert result.latency_ms is None


@pytest.mark.anyio
async def test_scan_port_returns_timeout_when_no_response():
    async def slow_connect(ip, port):
        await asyncio.sleep(0.3)
        raise AssertionError("should have timed out first")

    with patch(
        "app.discovery.port_scan.asyncio.open_connection", slow_connect
    ):
        result = await scan_port("10.0.5.1", 8080, timeout_s=0.05)

    assert result.status == "timeout"
    assert result.latency_ms is None


@pytest.mark.anyio
async def test_scan_port_returns_closed_on_other_os_error():
    with patch(
        "app.discovery.port_scan.asyncio.open_connection",
        AsyncMock(side_effect=OSError("network unreachable")),
    ):
        result = await scan_port("10.0.5.1", 22)

    assert result.status == "closed"


@pytest.mark.anyio
async def test_scan_port_rejects_invalid_port():
    with pytest.raises(ValueError):
        await scan_port("10.0.5.1", 0)

    with pytest.raises(ValueError):
        await scan_port("10.0.5.1", 70000)


@pytest.mark.anyio
async def test_scan_ports_returns_only_open_ports_from_given_list():
    async def fake_scan_port(ip: str, port: int, timeout_s: float):
        if port in (22, 443):
            return _open_result(port)
        return _closed_result(port)

    with patch(
        "app.discovery.port_scan.scan_port", AsyncMock(side_effect=fake_scan_port)
    ):
        results = await scan_ports("10.0.5.1", [21, 22, 443, 8080])

    assert {r.port for r in results} == {22, 443}
    assert all(r.status == "open" for r in results)


@pytest.mark.anyio
async def test_scan_ports_uses_common_ports_list_correctly():
    seen_ports = []

    async def fake_scan_port(ip: str, port: int, timeout_s: float):
        seen_ports.append(port)
        return _closed_result(port)

    with patch(
        "app.discovery.port_scan.scan_port", AsyncMock(side_effect=fake_scan_port)
    ):
        await scan_ports("10.0.5.1", COMMON_PORTS)

    assert sorted(seen_ports) == sorted(COMMON_PORTS)


@pytest.mark.anyio
async def test_scan_ports_limits_concurrency():
    active = 0
    max_active = 0

    async def fake_scan_port(ip: str, port: int, timeout_s: float):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        return _closed_result(port)

    with patch(
        "app.discovery.port_scan.scan_port", AsyncMock(side_effect=fake_scan_port)
    ):
        await scan_ports("10.0.5.1", COMMON_PORTS, port_concurrency=4)

    assert max_active == 4


@pytest.mark.anyio
async def test_scan_ports_continues_when_one_port_check_raises_unexpectedly():
    async def fake_scan_port(ip: str, port: int, timeout_s: float):
        if port == 22:
            raise RuntimeError("beklenmeyen hata")
        return _open_result(port) if port == 443 else _closed_result(port)

    with patch(
        "app.discovery.port_scan.scan_port", AsyncMock(side_effect=fake_scan_port)
    ):
        results = await scan_ports("10.0.5.1", [21, 22, 443])

    # 22'deki beklenmeyen hataya rağmen 443'ün sonucu kayboldu/scan
    # tamamen çökmedi.
    assert {r.port for r in results} == {443}


def _open_result(port: int):
    from app.discovery.schemas import PortResult

    return PortResult(port=port, status="open", latency_ms=1.0)


def _closed_result(port: int):
    from app.discovery.schemas import PortResult

    return PortResult(port=port, status="closed", latency_ms=None)
