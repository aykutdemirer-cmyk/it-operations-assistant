import socket
from unittest.mock import patch

import pytest

from app.discovery.dns_lookup import get_hostname


@pytest.mark.anyio
async def test_get_hostname_returns_name_on_success():
    with patch(
        "app.discovery.dns_lookup.socket.gethostbyaddr",
        return_value=("SERVER01", [], ["10.0.199.20"]),
    ):
        hostname = await get_hostname("10.0.199.20")

    assert hostname == "SERVER01"


@pytest.mark.anyio
async def test_get_hostname_returns_none_when_not_found():
    with patch(
        "app.discovery.dns_lookup.socket.gethostbyaddr",
        side_effect=socket.herror("host not found"),
    ):
        hostname = await get_hostname("10.0.199.99")

    assert hostname is None


@pytest.mark.anyio
async def test_get_hostname_returns_none_on_gaierror():
    with patch(
        "app.discovery.dns_lookup.socket.gethostbyaddr",
        side_effect=socket.gaierror("resolution failed"),
    ):
        hostname = await get_hostname("10.0.199.99")

    assert hostname is None


@pytest.mark.anyio
async def test_get_hostname_returns_none_on_timeout():
    import time

    def slow_lookup(ip: str):
        time.sleep(0.3)
        return ("TOO-SLOW", [], [ip])

    with patch(
        "app.discovery.dns_lookup.socket.gethostbyaddr", side_effect=slow_lookup
    ):
        hostname = await get_hostname("10.0.199.20", timeout_s=0.05)

    assert hostname is None


@pytest.mark.anyio
async def test_get_hostname_does_not_raise_on_unexpected_os_error():
    with patch(
        "app.discovery.dns_lookup.socket.gethostbyaddr",
        side_effect=OSError("unexpected"),
    ):
        hostname = await get_hostname("10.0.199.99")

    assert hostname is None
