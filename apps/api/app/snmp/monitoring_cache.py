"""Arka plan SNMP polling worker'ının (`scheduler.py`) doldurduğu,
süreç-içi (in-memory) bir önbellek.

`GET /api/monitoring` (Faz 24) her çağrıda YENİ bir poll turu çalıştırır
— bu davranış DEĞİŞMEDİ (AssetDetails'in "Şimdi Poll Et" gibi anlık
akışları buna bağımlı). Bu modül ONUN YERİNE geçmez; `GET /api/
monitoring/history`'nin (yeni) veri kaynağıdır — arka planda periyodik
olarak biriken poll GEÇMİŞİNİ (audit log) ve bant genişliği zaman
serisini tutar, "İzleme" sayfasının canlı grafik/log akışı için.

Kalıcı DEĞİLDİR — backend yeniden başladığında sıfırlanır. Bu,
`client.py::_LAST_SAMPLES` bant genişliği önbelleğiyle AYNI, bilinen ve
kabul edilmiş bir sınırlamadır (çoklu-worker/çoklu-process bir
dağıtımda paylaşılmaz)."""

from collections import deque
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.snmp.oid_map import INTERFACE_OIDS, SYSTEM_OIDS
from app.snmp.poller import PollBatchResult


class PollLogEntry(BaseModel):
    """Tek bir asset için tek bir poll denemesinin audit-log satırı —
    "Son Poll Logları" akışı için. Hiçbir credential/secret DEĞERİ
    taşımaz (yalnızca `SNMPPollResult`'ın zaten public alanları)."""

    asset_id: UUID
    status: str
    duration_ms: float | None
    oid_count: int
    polled_at: datetime
    error: str | None = None


class BandwidthSample(BaseModel):
    """Bir poll turunun TÜM asset/interface'leri üzerinden toplanan
    (aggregate) anlık bant genişliği örneği — bant genişliği zaman
    serisi grafiği için. Hiçbir interface'te gerçek bps verisi yoksa
    (ör. ilk poll, henüz baseline yok) dürüstçe `None` — asla 0 veya
    tahmini bir değer değil."""

    ts: datetime
    total_in_bps: float | None
    total_out_bps: float | None


_MAX_LOG_ENTRIES = 300
_MAX_BANDWIDTH_SAMPLES = 240  # varsayılan 30sn aralıkla ~2 saat

_latest_batch: PollBatchResult | None = None
_poll_log: deque[PollLogEntry] = deque(maxlen=_MAX_LOG_ENTRIES)
_bandwidth_history: deque[BandwidthSample] = deque(maxlen=_MAX_BANDWIDTH_SAMPLES)


def _oid_count_for(result) -> int:
    """Gerçek yapıdan türetilir, UYDURULMAZ: system alanları (varsa,
    `SYSTEM_OIDS` sayısı) + interface başına gerçekten sorgulanan kolon
    sayısı (`INTERFACE_OIDS`)."""
    count = len(SYSTEM_OIDS) if result.system else 0
    count += len(result.interfaces) * len(INTERFACE_OIDS)
    return count


def record_batch(batch: PollBatchResult) -> None:
    """Arka plan worker'ının (`scheduler.py`) her turdan sonra çağırdığı
    tek giriş noktası — önbelleği (son batch + log + bant genişliği
    zaman serisi) günceller."""
    global _latest_batch
    _latest_batch = batch

    total_in = 0.0
    total_out = 0.0
    any_bps = False
    for result in batch.results:
        _poll_log.appendleft(
            PollLogEntry(
                asset_id=result.asset_id,
                status=result.status,
                duration_ms=result.duration_ms,
                oid_count=_oid_count_for(result),
                polled_at=result.polled_at,
                error=result.error,
            )
        )
        for iface in result.interfaces:
            if iface.if_in_bps is not None:
                total_in += iface.if_in_bps
                any_bps = True
            if iface.if_out_bps is not None:
                total_out += iface.if_out_bps
                any_bps = True

    _bandwidth_history.append(
        BandwidthSample(
            ts=batch.completed_at,
            total_in_bps=total_in if any_bps else None,
            total_out_bps=total_out if any_bps else None,
        )
    )


def get_latest_batch() -> PollBatchResult | None:
    return _latest_batch


def get_poll_log(limit: int = 100) -> list[PollLogEntry]:
    return list(_poll_log)[:limit]


def get_bandwidth_history() -> list[BandwidthSample]:
    return list(_bandwidth_history)


def reset() -> None:
    """Yalnızca testler için — süreç-içi durumu temizler."""
    global _latest_batch
    _latest_batch = None
    _poll_log.clear()
    _bandwidth_history.clear()
