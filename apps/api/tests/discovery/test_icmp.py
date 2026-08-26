import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.discovery.icmp import ping_host


def _fake_process(returncode: int, wait_delay: float = 0.0) -> MagicMock:
    proc = MagicMock()

    async def _wait():
        if wait_delay:
            await asyncio.sleep(wait_delay)
        return returncode

    proc.wait = AsyncMock(side_effect=_wait)
    proc.kill = MagicMock()
    return proc


@pytest.mark.anyio
async def test_ping_host_returns_up_with_latency_when_reachable():
    proc = _fake_process(returncode=0)

    with patch(
        "app.discovery.icmp.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        result = await ping_host("10.0.5.1", timeout_ms=1000)

    assert result.ip == "10.0.5.1"
    assert result.status == "up"
    assert result.latency_ms is not None
    assert result.latency_ms >= 0


@pytest.mark.anyio
async def test_ping_host_returns_down_when_unreachable():
    proc = _fake_process(returncode=1)

    with patch(
        "app.discovery.icmp.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        result = await ping_host("10.0.5.3", timeout_ms=1000)

    assert result.status == "down"
    assert result.latency_ms is None


@pytest.mark.anyio
async def test_ping_host_returns_down_on_timeout():
    proc = _fake_process(returncode=0, wait_delay=1.0)

    with patch(
        "app.discovery.icmp.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        result = await ping_host("10.0.5.9", timeout_ms=10)

    assert result.status == "down"
    assert result.latency_ms is None
    proc.kill.assert_called_once()
