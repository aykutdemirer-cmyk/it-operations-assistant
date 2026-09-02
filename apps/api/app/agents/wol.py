"""Faz 37 — Wake-on-LAN. Backend, agent'ın bilinen MAC adresine bir
"magic packet" (UDP broadcast) gönderir — agent'ın KENDİSİYLE hiç
konuşmaz, cihaz kapalıyken bile çalışır (WoL'un bütün amacı bu). Bu
yalnızca standart WoL protokolünü UYGULAR — hedef donanımın (BIOS/
NIC'in "Wake on LAN" özelliği) bunu gerçekten desteklemesi/etkin
olması backend'in kontrolünde DEĞİLDİR; paket gönderildi diye cihazın
GERÇEKTEN uyanacağı garanti EDİLEMEZ, dürüstçe yalnızca "gönderildi"
raporlanır."""

from __future__ import annotations

import re
import socket

_MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$")

_WOL_PORT = 9  # Geleneksel "discard" portu — WoL için de facto standart.


class InvalidMacAddressError(Exception):
    """Verilen MAC adresi tanınan bir formatta değil — paket ASLA
    gönderilmez, sessizce "en iyi çaba" bir deneme yapılmaz."""


def _mac_to_bytes(mac_address: str) -> bytes:
    if not _MAC_RE.match(mac_address):
        raise InvalidMacAddressError(f"Geçersiz MAC adresi formatı: {mac_address!r}")
    hex_digits = mac_address.replace(":", "").replace("-", "")
    return bytes.fromhex(hex_digits)


def build_magic_packet(mac_address: str) -> bytes:
    """Standart WoL magic packet: 6 byte `0xFF` + hedef MAC'in 16 kez
    tekrarı (RFC yok, de facto AMD Magic Packet Technology formatı)."""
    mac_bytes = _mac_to_bytes(mac_address)
    return b"\xff" * 6 + mac_bytes * 16


def send_magic_packet(mac_address: str, broadcast_ip: str = "255.255.255.255") -> None:
    """UDP broadcast olarak magic packet'i gönderir. `SO_BROADCAST`
    olmadan işletim sistemi broadcast adresine gönderime izin vermez
    — bilinçli olarak yalnızca BU soket için etkinleştirilir, global
    bir ağ ayarı DEĞİŞTİRİLMEZ. Router'lar genelde broadcast trafiğini
    alt ağlar arasında YÖNLENDİRMEZ — bu, WoL'un kendi fiziksel/ağ
    kısıtıdır, kod burada bunu AŞAMAZ (dürüstçe belgelenir, bkz.
    docs/decisions.md)."""
    packet = build_magic_packet(mac_address)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast_ip, _WOL_PORT))
    finally:
        sock.close()
