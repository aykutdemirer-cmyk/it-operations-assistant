import asyncio

from app.discovery.arp import get_mac_address
from app.discovery.cidr import list_host_ips, parse_ipv4_cidr
from app.discovery.device_classifier import classify_device
from app.discovery.dns_lookup import get_hostname
from app.discovery.icmp import ping_host
from app.discovery.port_scan import COMMON_PORTS, scan_ports
from app.discovery.schemas import PingResult, ScanResult
from app.discovery.vendor import lookup_vendor

DEFAULT_CONCURRENCY = 50
DEFAULT_TIMEOUT_MS = 1000


async def scan_network(
    cidr: str,
    concurrency: int = DEFAULT_CONCURRENCY,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> ScanResult:
    network = parse_ipv4_cidr(cidr)
    host_ips = list_host_ips(network)

    semaphore = asyncio.Semaphore(concurrency)

    async def _ping_with_limit(ip: str) -> PingResult:
        async with semaphore:
            return await ping_host(ip, timeout_ms=timeout_ms)

    ping_results = await asyncio.gather(
        *(_ping_with_limit(ip) for ip in host_ips)
    )

    async def _enrich_up_host(result: PingResult) -> PingResult:
        if result.status != "up":
            return result

        try:
            async with semaphore:
                mac_address, hostname, open_ports = await asyncio.gather(
                    get_mac_address(result.ip),
                    get_hostname(result.ip),
                    scan_ports(result.ip, COMMON_PORTS),
                )
        except Exception:
            # Bir host'un zenginleştirme adımındaki beklenmedik bir hata
            # diğer host'ları etkilemez; ping sonucu olduğu gibi kalır.
            return result

        vendor = lookup_vendor(mac_address) if mac_address else None

        classification = classify_device(
            vendor=vendor,
            hostname=hostname,
            open_ports=[p.port for p in open_ports],
        )

        return result.model_copy(
            update={
                "mac_address": mac_address,
                "vendor": vendor,
                "hostname": hostname,
                "open_ports": open_ports,
                "device_type": classification.device_type,
                "confidence": classification.confidence,
                "evidence": classification.evidence,
            }
        )

    hosts = await asyncio.gather(*(_enrich_up_host(r) for r in ping_results))
    alive_hosts = sum(1 for host in hosts if host.status == "up")

    return ScanResult(
        cidr=str(network),
        total_hosts=len(host_ips),
        alive_hosts=alive_hosts,
        hosts=list(hosts),
    )
