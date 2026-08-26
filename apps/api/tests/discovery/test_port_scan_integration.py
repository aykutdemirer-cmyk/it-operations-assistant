"""Gerçek TCP bağlantısına dayalı testler — unit testlerden kasıtlı
olarak ayrı tutulur. Yalnızca loopback (127.0.0.1) kullanılır; dış ağa
veya kullanıcı yetkisi dışındaki bir hedefe hiçbir istek yapılmaz."""

import asyncio

import pytest

from app.discovery.port_scan import scan_port


@pytest.mark.anyio
async def test_scan_port_detects_a_real_open_local_port():
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        result = await scan_port("127.0.0.1", port, timeout_s=1.0)
    finally:
        server.close()
        await server.wait_closed()

    assert result.status == "open"
    assert result.latency_ms is not None


@pytest.mark.anyio
async def test_scan_port_does_not_report_open_for_unused_local_port():
    # 1 (tcpmux) bu makinede dinlenmiyor; "closed" ya da (Windows'ta bazı
    # portlar sessizce düşürüldüğü için) "timeout" olabilir — kritik olan
    # "open" DÖNMEMESİdir.
    result = await scan_port("127.0.0.1", 1, timeout_s=1.0)

    assert result.status in ("closed", "timeout")
