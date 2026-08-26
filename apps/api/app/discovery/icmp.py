import asyncio
import platform
import time

from app.discovery.schemas import PingResult

_IS_WINDOWS = platform.system() == "Windows"


def _build_ping_command(ip: str, timeout_ms: int) -> list[str]:
    if _IS_WINDOWS:
        return ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    timeout_s = max(1, round(timeout_ms / 1000))
    return ["ping", "-c", "1", "-W", str(timeout_s), ip]


async def ping_host(ip: str, timeout_ms: int = 1000) -> PingResult:
    """Bir host'un ICMP ile erişilebilirliğini kontrol eder.

    Windows'ta ham ICMP socket yönetici yetkisi gerektirdiğinden, işletim
    sisteminin kendi `ping` komutu subprocess ile çalıştırılır (admin
    gerektirmez). Gecikme, ping çıktısını parse etmek yerine (Windows
    yerelleştirmesine göre "time="/"süre=" gibi değişebildiğinden) komutun
    başlangıç-bitiş süresi ölçülerek hesaplanır.
    """
    command = _build_ping_command(ip, timeout_ms)
    start = time.monotonic()

    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    try:
        returncode = await asyncio.wait_for(
            proc.wait(), timeout=(timeout_ms / 1000) + 0.5
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return PingResult(ip=ip, status="down", latency_ms=None)

    if returncode != 0:
        return PingResult(ip=ip, status="down", latency_ms=None)

    latency_ms = round((time.monotonic() - start) * 1000, 1)
    return PingResult(ip=ip, status="up", latency_ms=latency_ms)
