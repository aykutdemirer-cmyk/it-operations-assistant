"""Arka plan SNMP polling worker'ı.

FastAPI `lifespan`'da başlatılır (`app/main.py`) — `asyncio.create_task`
ile TEK bir sürekli döngü, periyodik olarak `PollingEngine.poll_all`
çalıştırıp sonucu `monitoring_cache.record_batch`'e yazar. Bu, Ayarlar
sayfasındaki "SNMP Durumu"nu (bkz. `app/routes/health.py`) ve "İzleme"
sayfasının canlı grafik/log akışını (bkz. `app/routes/monitoring.py`
`/monitoring/history`) besler.

Tasarım ilkeleri (mevcut `poller.py` ile aynı):
- Bir turun hatası (DB erişilemez, beklenmeyen exception) worker'ı
  ASLA durdurmaz — loglanır, bir sonraki tur normal şekilde devam eder.
- `asyncio.CancelledError` hiçbir yerde yutulmaz — FastAPI shutdown'da
  `main.py` görevi `cancel()` eder, bu normal şekilde yukarı yayılır.
- Yalnızca `SNMP_BACKGROUND_POLLING_ENABLED=false` ile KAPATILABİLİR
  (varsayılan açık) — testler (`httpx.ASGITransport`) FastAPI lifespan
  event'lerini hiç tetiklemediği için zaten test izolasyonuna etkisi
  yok, ama gerçek bir deployment'ta kapatma imkânı bilinçli tutuldu."""

import asyncio
import logging
import os

from app.db.assets import get_connection, list_assets
from app.snmp.monitoring_cache import record_batch
from app.snmp.poller import PollingEngine

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_SECONDS = 30
_DEFAULT_ERROR_BACKOFF_SECONDS = 15


def is_background_polling_enabled() -> bool:
    raw = os.environ.get("SNMP_BACKGROUND_POLLING_ENABLED", "true")
    return raw.strip().lower() not in ("0", "false", "no")


def _interval_seconds() -> int:
    raw = os.environ.get("SNMP_POLL_INTERVAL_SECONDS")
    if not raw:
        return _DEFAULT_INTERVAL_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_INTERVAL_SECONDS
    return value if value > 0 else _DEFAULT_INTERVAL_SECONDS


async def _run_once() -> None:
    try:
        conn = await get_connection()
    except OSError:
        logger.warning("Arka plan SNMP poll turu atlandı — PostgreSQL erişilemedi")
        return

    try:
        assets = await list_assets(conn)
        batch = await PollingEngine().poll_all(assets, conn)
        record_batch(batch)
        logger.info(
            "Arka plan SNMP poll turu tamamlandı: total=%d polled=%d not_configured=%d",
            batch.total, batch.polled, batch.not_configured,
        )
    except Exception:
        logger.exception("Arka plan SNMP poll turu beklenmeyen bir hatayla başarısız oldu")
    finally:
        await conn.close()


async def run_background_poller() -> None:
    """Sonsuz döngü — `app/main.py::lifespan` tarafından bir
    `asyncio.Task` olarak başlatılır, shutdown'da `task.cancel()` ile
    durdurulur (`CancelledError` burada YUTULMAZ, normal şekilde
    yayılır — görev iptali `except asyncio.CancelledError` YOK)."""
    interval = _interval_seconds()
    logger.info("Arka plan SNMP polling worker başlatıldı (interval=%ss)", interval)
    while True:
        await _run_once()
        await asyncio.sleep(interval)
