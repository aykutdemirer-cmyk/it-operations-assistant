from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.discovery.arp import get_mac_address

ARP_OUTPUT = b"""
Interface: 10.0.199.13 --- 0xe
  Internet Address      Physical Address      Type
  10.0.199.1             aa-bb-cc-dd-ee-ff     dynamic
"""


def _fake_process(returncode: int, stdout: bytes) -> MagicMock:
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(stdout, b""))
    proc.returncode = returncode
    return proc


@pytest.mark.anyio
async def test_get_mac_address_returns_mac_when_ip_in_arp_table():
    proc = _fake_process(returncode=0, stdout=ARP_OUTPUT)

    with patch(
        "app.discovery.arp.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        mac = await get_mac_address("10.0.199.1")

    assert mac == "AA-BB-CC-DD-EE-FF"


@pytest.mark.anyio
async def test_get_mac_address_returns_none_when_ip_not_in_arp_table():
    proc = _fake_process(returncode=0, stdout=ARP_OUTPUT)

    with patch(
        "app.discovery.arp.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        mac = await get_mac_address("10.0.199.99")

    assert mac is None


@pytest.mark.anyio
async def test_get_mac_address_returns_none_when_arp_command_fails():
    proc = _fake_process(returncode=1, stdout=b"")

    with patch(
        "app.discovery.arp.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ):
        mac = await get_mac_address("10.0.199.1")

    assert mac is None
