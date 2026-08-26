"""Gerçek DNS/sistem resolver'ına bağlı test — unit testlerden kasıtlı
olarak ayrı tutulur. `127.0.0.1` her ortamda reverse-resolve edilebilir
olduğundan dış ağa bağımlılık oluşturmaz (Windows'ta genellikle makine
adına çözülür)."""

import pytest

from app.discovery.dns_lookup import get_hostname


@pytest.mark.anyio
async def test_get_hostname_resolves_loopback():
    hostname = await get_hostname("127.0.0.1")

    assert hostname is not None
    assert len(hostname) > 0
