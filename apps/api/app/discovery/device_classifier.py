from dataclasses import dataclass
from typing import Callable, Literal

DeviceType = Literal[
    "firewall",
    "router",
    "switch",
    "server",
    "workstation",
    "printer",
    "access_point",
    "camera",
    "nas",
    "network_device",
    "unknown",
]
Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class ClassificationResult:
    device_type: DeviceType
    confidence: Confidence
    evidence: list[str]


@dataclass(frozen=True)
class DeviceEvidence:
    """Sınıflandırma kurallarının girdisi: discovery'nin topladığı ham
    gerçekler. Bu modül discovery scanner'ından bağımsızdır — yalnızca
    zaten toplanmış veriyi (vendor/hostname/açık portlar) değerlendirir,
    kendi ağ isteği yapmaz."""

    vendor: str | None
    hostname: str | None
    open_ports: list[int]


def _vendor_contains(vendor: str | None, keyword: str) -> bool:
    return vendor is not None and keyword.lower() in vendor.lower()


def _rule_fortinet(e: DeviceEvidence) -> ClassificationResult | None:
    if _vendor_contains(e.vendor, "fortinet"):
        return ClassificationResult("firewall", "high", ["vendor: Fortinet"])
    return None


def _rule_palo_alto(e: DeviceEvidence) -> ClassificationResult | None:
    if _vendor_contains(e.vendor, "palo alto"):
        return ClassificationResult("firewall", "high", ["vendor: Palo Alto"])
    return None


def _rule_cisco_network_device(e: DeviceEvidence) -> ClassificationResult | None:
    if _vendor_contains(e.vendor, "cisco") and 22 in e.open_ports and 443 in e.open_ports:
        return ClassificationResult(
            "network_device", "medium", ["vendor: Cisco", "port: 22", "port: 443"]
        )
    return None


def _rule_ambiguous_windows_ports(e: DeviceEvidence) -> ClassificationResult | None:
    # 3389 (RDP) + 445 (SMB) workstation ile server'ı güvenilir şekilde
    # ayırt etmez; yeni bir "windows" türü icat etmek yerine yanlış
    # pozitif üretmemek için unknown/low döneriz (evidence korunur).
    if 3389 in e.open_ports and 445 in e.open_ports:
        return ClassificationResult("unknown", "low", ["port: 3389", "port: 445"])
    return None


@dataclass(frozen=True)
class Rule:
    id: str
    priority: int
    match: Callable[[DeviceEvidence], ClassificationResult | None]


# Öncelik: 1) vendor-specific güçlü kurallar, 2) güçlü servis/port
# kombinasyonları, 3) genel network-device kuralları (şu an MVP'de yok),
# 4) unknown (varsayılan, aşağıda ayrıca ele alınır).
_RULES: list[Rule] = [
    Rule("vendor-fortinet", 1, _rule_fortinet),
    Rule("vendor-palo-alto", 1, _rule_palo_alto),
    Rule("cisco-network-device", 2, _rule_cisco_network_device),
    Rule("ambiguous-windows-ports", 2, _rule_ambiguous_windows_ports),
]

_UNKNOWN_NO_EVIDENCE = ClassificationResult("unknown", "low", [])


def classify_device(
    vendor: str | None = None,
    hostname: str | None = None,
    open_ports: list[int] | None = None,
) -> ClassificationResult:
    """Toplanmış discovery verisinden (vendor/hostname/açık portlar)
    deterministic, kural tabanlı cihaz türü tahmini yapar. AI/LLM/dış
    servis kullanmaz. Kurallar öncelik sırasına göre değerlendirilir;
    ilk eşleşen kural kazanır ve yalnızca onun evidence'ı döner. Hiçbir
    kural eşleşmezse `unknown`/`low`/boş evidence döner."""
    evidence = DeviceEvidence(
        vendor=vendor, hostname=hostname, open_ports=open_ports or []
    )

    for rule in sorted(_RULES, key=lambda r: r.priority):
        result = rule.match(evidence)
        if result is not None:
            return result

    return _UNKNOWN_NO_EVIDENCE
