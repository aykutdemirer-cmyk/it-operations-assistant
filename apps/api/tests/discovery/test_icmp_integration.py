"""Gerçek ağa (loopback) bağlı testler — unit testlerden kasıtlı olarak
ayrı tutulur. `127.0.0.1` her ortamda erişilebilir olduğundan dış ağa
bağımlılık oluşturmaz."""

import pytest

from app.discovery.icmp import ping_host


@pytest.mark.anyio
async def test_ping_host_reaches_localhost():
    result = await ping_host("127.0.0.1", timeout_ms=1000)

    assert result.status == "up"
    assert result.latency_ms is not None
