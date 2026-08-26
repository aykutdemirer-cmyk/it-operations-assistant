import asyncio
import time

from app.discovery.schemas import PortResult

# Kolayca değiştirilebilir yaygın IT port listesi (bkz. FAZ 2.5).
COMMON_PORTS: list[int] = [
    21,
    22,
    23,
    25,
    53,
    80,
    110,
    135,
    139,
    143,
    443,
    445,
    3389,
    5900,
    5985,
    5986,
    8080,
    8443,
]

DEFAULT_PORT_TIMEOUT_S = 0.5
DEFAULT_PORT_CONCURRENCY = 10


async def scan_port(
    ip: str, port: int, timeout_s: float = DEFAULT_PORT_TIMEOUT_S
) -> PortResult:
    """Bir port için salt-okunur TCP connect denemesi yapar; bağlantı
    kurulur kurulmaz kapatılır. Veri gönderilmez, authentication veya
    banner grabbing yapılmaz. Ham socket kullanılmaz — standart
    `asyncio.open_connection` (stdlib) ile, Windows'ta yönetici yetkisi
    gerektirmeden çalışır."""
    if not (1 <= port <= 65535):
        raise ValueError(f"Geçersiz port: {port}")

    start = time.monotonic()

    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=timeout_s
        )
    except asyncio.TimeoutError:
        return PortResult(port=port, status="timeout", latency_ms=None)
    except OSError:
        # ConnectionRefusedError dahil: port kapalı/erişilemez.
        return PortResult(port=port, status="closed", latency_ms=None)

    latency_ms = round((time.monotonic() - start) * 1000, 1)
    writer.close()
    await writer.wait_closed()
    return PortResult(port=port, status="open", latency_ms=latency_ms)


async def scan_ports(
    ip: str,
    ports: list[int],
    port_concurrency: int = DEFAULT_PORT_CONCURRENCY,
    timeout_s: float = DEFAULT_PORT_TIMEOUT_S,
) -> list[PortResult]:
    """Verilen port listesini kontrollü concurrency ile tarar ve yalnızca
    açık portları döner (kapalı/timeout olanlar sonuç listesine dahil
    edilmez). Bir portun taranmasındaki beklenmedik bir hata diğer
    portların taranmasını durdurmaz."""
    semaphore = asyncio.Semaphore(port_concurrency)

    async def _scan_with_limit(port: int) -> PortResult | None:
        async with semaphore:
            try:
                return await scan_port(ip, port, timeout_s=timeout_s)
            except Exception:
                return None

    results = await asyncio.gather(*(_scan_with_limit(p) for p in ports))
    return [r for r in results if r is not None and r.status == "open"]
