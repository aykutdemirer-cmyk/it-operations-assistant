"""Agent ↔ Asset eşleştirme değerlendirmesi (Faz 29).

Bu modül SALT-OKUNUR bir DEĞERLENDİRME katmanıdır — hiçbir DB yazması
yapmaz, `agents.asset_id`'yi hiçbir zaman kendiliğinden doldurmaz.
Yalnızca hostname/IP/MAC tek başına eşleşmesi ("tek sinyal") YETERSİZ
kabul edilir (kullanıcının açık talebi: "Bu fazda güvenilir olmayan
otomatik eşleştirme yapma") — bunlar ayrı ayrı değişebilir/yeniden
kullanılabilir (DHCP IP rotasyonu, hostname yeniden adlandırma, MAC
spoofing/sanallaştırma). Yalnızca BİRDEN FAZLA bağımsız sinyalin AYNI
asset'i işaret ettiği durum `confirmed` sayılır; tek sinyal `candidate`
(insan onayı bekler); hiç sinyal yoksa `unmatched`.

Gerçek DB'ye yazma yalnızca `app/routes/agents.py`'nin ayrı, açık bir
"confirm" endpoint'i üzerinden — bu modülün ürettiği bir `candidate`/
`confirmed` sonucunu insan/çağıran taraf açıkça onayladığında olur."""

from typing import Literal

from pydantic import BaseModel

MatchConfidence = Literal["confirmed", "candidate", "unmatched"]


class AssetMatchCandidate(BaseModel):
    asset_id: str | None
    confidence: MatchConfidence
    matched_signals: list[str]
    reason: str


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def evaluate_asset_match(agent_row: dict, candidate_assets: list[dict]) -> AssetMatchCandidate:
    """`agent_row` (bkz. `app/db/agents.py::get_agent_by_id`) için
    `candidate_assets` (bkz. `app/db/assets.py::list_assets`) arasından
    en iyi eşleşmeyi DEĞERLENDİRİR — hiçbir şey UYGULAMAZ."""
    agent_hostname = _normalize(agent_row.get("hostname"))
    agent_ip = _normalize(agent_row.get("local_ip"))
    agent_mac = _normalize(agent_row.get("mac_address"))

    best_single_signal: AssetMatchCandidate | None = None

    for asset in candidate_assets:
        asset_hostname = _normalize(asset.get("hostname"))
        asset_ip = _normalize(str(asset.get("ip_address")) if asset.get("ip_address") else None)
        asset_mac = _normalize(asset.get("mac_address"))

        signals: list[str] = []
        if agent_hostname and agent_hostname == asset_hostname:
            signals.append("hostname")
        if agent_ip and agent_ip == asset_ip:
            signals.append("ip")
        if agent_mac and agent_mac == asset_mac:
            signals.append("mac_address")

        if len(signals) >= 2:
            return AssetMatchCandidate(
                asset_id=str(asset["id"]),
                confidence="confirmed",
                matched_signals=signals,
                reason=(
                    f"{len(signals)} bağımsız sinyal eşleşti "
                    f"({', '.join(signals)}) — güvenilir eşleşme."
                ),
            )
        if len(signals) == 1 and best_single_signal is None:
            best_single_signal = AssetMatchCandidate(
                asset_id=str(asset["id"]),
                confidence="candidate",
                matched_signals=signals,
                reason=(
                    f"Yalnızca tek bir sinyal eşleşti ({signals[0]}) — "
                    "tek başına güvenilir kabul edilmez, insan onayı gerekir."
                ),
            )

    if best_single_signal is not None:
        return best_single_signal

    return AssetMatchCandidate(
        asset_id=None,
        confidence="unmatched",
        matched_signals=[],
        reason="Hiçbir asset ile eşleşen sinyal (hostname/IP/MAC) bulunamadı.",
    )
