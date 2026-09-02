"""Network interface envanteri/telemetry — bu proje için özellikle
kritik bir collector (bkz. FAZ 30 master prompt §8). Her interface için
normalize edilmiş, `apps/api/app/agents/models.py::
NetworkInterfaceSample` ile birebir alan adları taşıyan bir dict
üretir. Ethernet/Wi-Fi/loopback/Docker/VPN gibi interface TİPLERİNİ
isim tabanlı bir kalıp eşleştirmeyle ayırt eder — %100 kesin değildir
(işletim sistemi interface isimlendirmesi standart değildir), bu yüzden
sonuç `interface_type` alanına yazılır ama hiçbir zaman kesin bir
gerçek olarak sunulmaz; eşleşmeyen isimler dürüstçe `"other"` kalır."""

from __future__ import annotations

import logging
import socket

import psutil

logger = logging.getLogger("agent.collectors.network")

_LOOPBACK_PREFIXES = ("lo",)
_LOOPBACK_NAMES_CONTAIN = ("loopback",)
_WIFI_NAMES_CONTAIN = ("wi-fi", "wifi", "wlan", "wireless")
_DOCKER_NAMES_CONTAIN = ("docker", "veth", "br-", "cni", "flannel")
_VIRTUAL_NAMES_CONTAIN = ("vethernet", "hyper-v", "virtualbox", "vmware", "vnic")
_VPN_NAMES_CONTAIN = ("vpn", "tap", "tun", "wireguard", "openvpn", "ppp")
_ETHERNET_NAMES_CONTAIN = ("ethernet", "eth", "enp", "eno", "ens")


def classify_interface_type(name: str) -> str:
    lowered = name.lower()
    if lowered.startswith(_LOOPBACK_PREFIXES) or any(n in lowered for n in _LOOPBACK_NAMES_CONTAIN):
        return "loopback"
    if any(n in lowered for n in _WIFI_NAMES_CONTAIN):
        return "wifi"
    if any(n in lowered for n in _DOCKER_NAMES_CONTAIN):
        return "docker"
    if any(n in lowered for n in _VIRTUAL_NAMES_CONTAIN):
        return "virtual"
    if any(n in lowered for n in _VPN_NAMES_CONTAIN):
        return "vpn"
    if any(n in lowered for n in _ETHERNET_NAMES_CONTAIN):
        return "ethernet"
    return "other"


def _primary_ipv4(addresses: list[str], all_addrs: list) -> str | None:
    for addr in all_addrs:
        if addr.family == socket.AF_INET:
            return addr.address
    return None


def collect_interfaces() -> list[dict]:
    """Tüm interface'ler için envanter/telemetry'nin İKİSİNE de yetecek
    zengin bir dict listesi döner — `inventory.py`/`telemetry.py` bu
    tek listeden kendi ihtiyaç duydukları alt kümeyi alır (aynı veriyi
    iki kez toplamamak için)."""
    try:
        addrs_by_name = psutil.net_if_addrs()
    except Exception:
        logger.warning("Network interface adresleri alınamadı", exc_info=True)
        return []

    try:
        stats_by_name = psutil.net_if_stats()
    except Exception:
        stats_by_name = {}

    try:
        io_by_name = psutil.net_io_counters(pernic=True)
    except Exception:
        io_by_name = {}

    interfaces: list[dict] = []
    for name, addr_list in addrs_by_name.items():
        addresses = [a.address for a in addr_list if a.family in (socket.AF_INET, socket.AF_INET6)]
        mac_address = next(
            (a.address for a in addr_list if a.family == psutil.AF_LINK and a.address), None
        )

        stats = stats_by_name.get(name)
        io = io_by_name.get(name)

        interfaces.append(
            {
                "name": name,
                "interface_type": classify_interface_type(name),
                "ip_address": _primary_ipv4(addresses, addr_list),
                "addresses": addresses,
                "mac_address": mac_address,
                "state": "up" if (stats and stats.isup) else ("down" if stats else None),
                "speed_bps": (stats.speed * 1_000_000) if (stats and stats.speed > 0) else None,
                "rx_bytes": io.bytes_recv if io else None,
                "tx_bytes": io.bytes_sent if io else None,
                "rx_errors": io.errin if io else None,
                "tx_errors": io.errout if io else None,
            }
        )
    return interfaces
