import json
import re
from functools import lru_cache
from pathlib import Path

_DATASET_PATH = Path(__file__).parent / "data" / "oui.json"
_OCTET_RE = re.compile(r"^[0-9a-fA-F]{2}$")


@lru_cache(maxsize=1)
def _load_dataset() -> dict[str, str]:
    """OUI -> vendor eşlemesini yalnızca bir kez, lokal `oui.json`
    dosyasından okur (bkz. `data/OUI_DATASET.md`). Runtime'da hiçbir
    ağ isteği yapılmaz."""
    with _DATASET_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def extract_oui(mac: str) -> str | None:
    """Bir MAC adresinin ilk 3 octet'ini (OUI) çıkarıp `AA-BB-CC`
    biçiminde normalize eder. `-`, `:` veya boşluk ayraçlı girdileri
    büyük/küçük harf duyarsız kabul eder. Geçersiz girdide `None` döner
    (hata fırlatmaz — discovery adımı arayüzü)."""
    octets = [o for o in re.split(r"[:\-\s]+", mac.strip()) if o]

    if len(octets) < 3:
        return None

    first_three = octets[:3]
    if not all(_OCTET_RE.match(o) for o in first_three):
        return None

    return "-".join(o.upper() for o in first_three)


def lookup_vendor(mac: str) -> str | None:
    """Bir MAC adresi için lokal IEEE OUI dataset'inden üretici adını
    döner. Vendor tahmin edilmez/üretilmez; yalnızca dataset'te birebir
    eşleşen bir kayıt varsa döner, yoksa `None`."""
    oui = extract_oui(mac)
    if oui is None:
        return None

    key = oui.replace("-", "")
    return _load_dataset().get(key)
