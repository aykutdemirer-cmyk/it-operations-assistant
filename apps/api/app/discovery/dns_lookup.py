import asyncio
import socket

DEFAULT_TIMEOUT_S = 2.0


async def get_hostname(ip: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> str | None:
    """Bir IP için reverse DNS (PTR) ile hostname çözer.

    `socket.gethostbyaddr`, işletim sisteminin (Windows dahil) yerel
    resolver'ını kullanır — bloklayan bir çağrı olduğundan thread
    executor'da çalıştırılır ve `asyncio.wait_for` ile zaman aşımına
    tabi tutulur. Çözülemezse (bulunamadı, timeout, beklenmedik hata)
    `None` döner; hiçbir zaman exception fırlatmaz — bir host'un DNS
    hatası taramanın geri kalanını durdurmaz (discovery adımı arayüzü,
    bkz. CLAUDE.md)."""
    loop = asyncio.get_event_loop()

    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, socket.gethostbyaddr, ip),
            timeout=timeout_s,
        )
    except (socket.herror, socket.gaierror, asyncio.TimeoutError, OSError):
        return None

    hostname, _aliases, _addresses = result
    return hostname
