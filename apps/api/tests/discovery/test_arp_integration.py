"""Gerçek Windows `arp` komutuna bağlı test — unit testlerden kasıtlı
olarak ayrı tutulur. Loopback adresi ARP tablosunda hiçbir zaman yer
almadığından sonuç her ortamda deterministik olarak `None` olur."""

import pytest

from app.discovery.arp import get_mac_address


@pytest.mark.anyio
async def test_get_mac_address_returns_none_for_loopback():
    mac = await get_mac_address("127.0.0.1")

    assert mac is None
