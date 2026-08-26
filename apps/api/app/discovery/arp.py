import asyncio
import re

_ARP_LINE_RE = re.compile(
    r"(?P<ip>\d{1,3}(?:\.\d{1,3}){3})\s+"
    r"(?P<mac>[0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5})"
)


def normalize_mac(mac: str) -> str:
    octets = re.split(r"[:-]", mac)
    return "-".join(octet.upper() for octet in octets)


def parse_arp_output(output: str) -> dict[str, str]:
    """Windows `arp -a` çıktısını IP -> normalize edilmiş MAC eşlemesine
    çevirir. Sütun başlıkları Windows diline göre değişir (İnternet
    Adresi/Internet Address gibi); bu yüzden başlık metnine değil, her
    satırdaki IP + MAC veri deseninin kendisine bakılır."""
    entries: dict[str, str] = {}
    for line in output.splitlines():
        match = _ARP_LINE_RE.search(line)
        if not match:
            continue
        entries[match.group("ip")] = normalize_mac(match.group("mac"))
    return entries


async def get_mac_address(ip: str) -> str | None:
    """Belirtilen IP için Windows ARP tablosundan MAC adresini okur.

    Yalnızca ARP tablosunda zaten bulunan (aynı L2 segmentinde, daha önce
    iletişim kurulmuş) girdileri okur — MAC tahmin etmez, üretmez. Bulunamazsa
    `None` döner; bu bir hata değildir (bkz. discovery adımı arayüzü,
    CLAUDE.md)."""
    proc = await asyncio.create_subprocess_exec(
        "arp",
        "-a",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()

    if proc.returncode != 0:
        return None

    entries = parse_arp_output(stdout.decode(errors="ignore"))
    return entries.get(ip)

