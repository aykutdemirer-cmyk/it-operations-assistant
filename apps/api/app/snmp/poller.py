"""SNMP polling engine (Faz 23, Faz 29.5'te DB-tabanlı profil çözümüne
bağlandı).

Akış: asset listesi -> her asset için `profile_store.
resolve_profile_for_asset` (conn verilmişse önce `asset_snmp_profiles`
DB ataması, yoksa `.env` fallback) -> profil varsa `SNMPClient.
poll_asset` -> `SNMPPollResult`. Profil yoksa asset ATLANMAZ — mevcut
tek-asset `POST /api/snmp/poll/{asset_id}` davranışıyla tutarlı, dürüst
bir `not_configured` sonucu üretilir (bkz. `app/routes/snmp.py`).

Tasarım kısıtları (kullanıcı talimatı):
- Eşzamanlılık `SNMP_MAX_CONCURRENCY` ile sınırlanır — sınırsız paralel
  poll YAPILMAZ. Varsayılan düşük, güvenli bir değer (`_DEFAULT_MAX_
  CONCURRENCY`).
- Bir cihazın hatası/timeout'u diğerlerini ASLA durdurmaz — her poll
  kendi try/except'i içinde izole edilir; hiçbir ham exception/detay
  dışarı sızmaz (mevcut `client.py`/`routes/snmp.py` ile aynı ilke).
- `asyncio.CancelledError` hiçbir yerde yutulmaz — görev iptali
  (graceful shutdown, çağıranın `task.cancel()`'ı) her zaman normal
  şekilde yukarı yayılır; bu sayede FastAPI'nin kendi request/shutdown
  lifecycle'ı bozulmaz.
- Bu modül yeni bir `SNMPPollResult.status` değeri EKLEMEZ — mevcut altı
  değer (not_configured/unreachable/timeout/authentication_failed/
  success/partial) batch modunda da aynen kullanılır; yalnızca
  `PollBatchResult` adında YENİ bir sarmalayıcı tip ekler (toplam/
  polled/not_configured sayıları + zamanlama), tekil sözleşmeyi
  değiştirmez.

`GET /api/monitoring` (Faz 24, `app/routes/monitoring.py`) bu engine'i
tüm asset listesiyle çağırır. Tek-asset canlı poll için hâlâ
`POST /api/snmp/poll/{asset_id}` kullanılır — bu ikisi birbirinin
YERİNE geçmez (bkz. `routes/monitoring.py` docstring'i)."""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel

from app.snmp.client import SNMPClient
from app.snmp.models import SNMPPollResult
from app.snmp.profile_store import resolve_profile_for_asset

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CONCURRENCY = 5


def _max_concurrency_from_env() -> int:
    raw = os.environ.get("SNMP_MAX_CONCURRENCY")
    if not raw:
        return _DEFAULT_MAX_CONCURRENCY
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_CONCURRENCY
    return value if value > 0 else _DEFAULT_MAX_CONCURRENCY


class PollBatchResult(BaseModel):
    """Bir `poll_all` çağrısının toplu sonucu. Tekil `SNMPPollResult`
    sözleşmesini değiştirmez, yalnızca onu zamanlama/sayım bilgisiyle
    sarar."""

    started_at: datetime
    completed_at: datetime
    duration_ms: float
    total: int
    polled: int  # gerçekten bir profille poll edilenler (not_configured hariç)
    not_configured: int
    results: list[SNMPPollResult]


class PollingEngine:
    """`await PollingEngine().poll_all(assets)` — her asset için profil
    çözer, varsa gerçek poll yapar, `SNMP_MAX_CONCURRENCY` (veya
    kurucuya açıkça verilen bir değer) ile sınırlı eşzamanlılıkla.

    `assets`: `app.db.assets.list_assets`'in döndürdüğü ham dict
    listesi (en az `id`/`ip_address` alanları kullanılır) — bu modül
    DB'ye doğrudan erişmez, çağıran taraf (route/scheduler) sağlar."""

    def __init__(self, max_concurrency: int | None = None, client: SNMPClient | None = None):
        self._max_concurrency = (
            max_concurrency if max_concurrency is not None else _max_concurrency_from_env()
        )
        self._client = client or SNMPClient()

    async def poll_all(self, assets: list[dict], conn=None) -> PollBatchResult:
        """`conn` verilirse (Faz 29.5) her asset için önce
        `asset_snmp_profiles` DB ataması denenir; verilmezse (mevcut
        çağıranlarla geriye dönük uyumluluk) yalnızca `.env` tabanlı
        tek-hedef fallback kullanılır — bkz. `resolve_profile_for_asset`.

        Profil çözümü ÖNCE, SIRAYLA yapılır (tek bir `asyncpg.Connection`
        aynı anda yalnızca bir sorguyu destekler — `asyncio.gather` ile
        eşzamanlı çağrılırsa `InterfaceError: another operation is in
        progress` fırlatır); yalnızca gerçek SNMP ağ poll'ları
        (`SNMPClient.poll_asset`, DB'ye dokunmaz) `SNMP_MAX_CONCURRENCY`
        ile sınırlı eşzamanlılıkla çalışır."""
        started = time.monotonic()
        started_at = _now()
        semaphore = asyncio.Semaphore(self._max_concurrency)

        logger.debug(
            "SNMP polling engine başlıyor: asset_sayisi=%d max_concurrency=%d",
            len(assets), self._max_concurrency,
        )

        profiles = {}
        for asset in assets:
            profiles[asset["id"]] = await resolve_profile_for_asset(conn, asset)

        results = await asyncio.gather(
            *(self._poll_one(asset, semaphore, profiles[asset["id"]]) for asset in assets)
        )

        not_configured_count = sum(1 for r in results if r.status == "not_configured")
        completed_at = _now()
        logger.info(
            "SNMP polling engine tamamlandı: total=%d polled=%d not_configured=%d duration_ms=%.1f",
            len(results), len(results) - not_configured_count, not_configured_count, _elapsed_ms(started),
        )
        return PollBatchResult(
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=_elapsed_ms(started),
            total=len(results),
            polled=len(results) - not_configured_count,
            not_configured=not_configured_count,
            results=list(results),
        )

    async def _poll_one(
        self, asset: dict, semaphore: asyncio.Semaphore, profile: object | None
    ) -> SNMPPollResult:
        asset_id: UUID = asset["id"]
        host: str = asset["ip_address"]
        try:
            if profile is None:
                return SNMPPollResult(
                    asset_id=asset_id,
                    polled_at=_now(),
                    status="not_configured",
                    error="SNMP credential/community bu asset için henüz yapılandırılmadı.",
                )
            async with semaphore:
                return await self._client.poll_asset(profile, host, asset_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Bir cihazın BEKLENMEYEN hatası diğerlerini asla durdurmaz —
            # ama gerçek library/exception detayı da dışarı sızdırılmaz.
            logger.exception("SNMP poll beklenmeyen şekilde başarısız (asset_id=%s)", asset_id)
            return SNMPPollResult(
                asset_id=asset_id,
                polled_at=_now(),
                status="unreachable",
                error="SNMP poll sırasında beklenmeyen bir hata oluştu.",
            )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _elapsed_ms(started: float) -> float:
    return (time.monotonic() - started) * 1000
