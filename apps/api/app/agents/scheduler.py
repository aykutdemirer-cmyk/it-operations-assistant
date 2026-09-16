"""Arka plan Agent Bakım (Maintenance) worker'ı.

FastAPI `lifespan`'da başlatılır (`app/main.py`) — `app/snmp/
scheduler.py`'nin AYNI tasarım ilkelerini paylaşan, ayrı bir sürekli
döngü. Her turda iki bağımsız iş yapar (biri başarısız olsa diğeri
etkilenmez):

1. **İnaktif agent arşivleme** — `agent_retention_policy` (Ayarlar >
   Agent Yapılandırması'ndaki "İnaktif Agent Otomatik Temizleme" UI'si
   tarafından yazılır, bkz. `app/routes/agents.py`) `enabled=true` VE
   bir agent `retention_days`'ten uzun süredir heartbeat GÖNDERMEMİŞSE
   agent'ı arşivler (soft-delete, bkz. `app/db/agents.py::
   archive_agent`) — HİÇBİR ZAMAN kalıcı olarak SİLİNMEZ, `/agents`
   sayfasının "Arşiv" sekmesinden geri yüklenebilir. Politika
   `enabled=false` (varsayılan) iken bu adım tamamen atlanır —
   `ENABLE_REMOTE_COMMANDS` ile AYNI opt-in ilkesi.
2. **Süresi dolmuş telemetry temizliği** — `app/agents/service.py::
   cleanup_expired_telemetry` (Faz 29'da yazıldı, o zamandan beri
   hiçbir zamanlayıcıya bağlı değildi — bkz. o fonksiyonun docstring'i)
   artık burada periyodik çalışıyor.

Tasarım ilkeleri (mevcut `app/snmp/scheduler.py` ile AYNI):
- Bir turun hatası (DB erişilemez, beklenmeyen exception) worker'ı
  ASLA durdurmaz.
- `asyncio.CancelledError` hiçbir yerde yutulmaz.
- Worker'ın KENDİSİ yalnızca `AGENT_MAINTENANCE_ENABLED=false` ile
  kapatılabilir (varsayılan açık) — testler lifespan'ı hiç
  tetiklemediği için test izolasyonuna etkisi YOK. Worker açık olsa
  bile GERÇEK arşivleme yalnızca yukarıdaki DB politikası
  `enabled=true` iken gerçekleşir — iki AYRI anahtar."""

import asyncio
import logging
import os

from app.agents.service import cleanup_expired_telemetry
from app.db.agents import archive_agent, get_connection, get_retention_policy, list_inactive_agent_ids

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_SECONDS = 3600  # 1 saat — inaktiflik/telemetry temizliği saniyelik hassasiyet gerektirmez


def is_agent_maintenance_enabled() -> bool:
    raw = os.environ.get("AGENT_MAINTENANCE_ENABLED", "true")
    return raw.strip().lower() not in ("0", "false", "no")


def _interval_seconds() -> int:
    raw = os.environ.get("AGENT_MAINTENANCE_INTERVAL_SECONDS")
    if not raw:
        return _DEFAULT_INTERVAL_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_INTERVAL_SECONDS
    return value if value > 0 else _DEFAULT_INTERVAL_SECONDS


async def _archive_inactive_agents(conn) -> int:
    policy = await get_retention_policy(conn)
    if not policy["enabled"]:
        return 0
    retention_days = policy["retention_days"]
    inactive_ids = await list_inactive_agent_ids(conn, retention_days)
    for agent_id in inactive_ids:
        await archive_agent(conn, agent_id, reason="inactivity", inactive_days=retention_days)
    if inactive_ids:
        logger.info(
            "Arka plan bakım: %d inaktif agent arşivlendi (retention_days=%d)",
            len(inactive_ids), retention_days,
        )
    return len(inactive_ids)


async def _run_once() -> None:
    try:
        conn = await get_connection()
    except OSError:
        logger.warning("Arka plan Agent bakım turu atlandı — PostgreSQL erişilemedi")
        return

    try:
        try:
            await _archive_inactive_agents(conn)
        except Exception:
            logger.exception("Arka plan bakım: inaktif agent arşivleme başarısız oldu")

        try:
            deleted = await cleanup_expired_telemetry(conn)
            if deleted:
                logger.info("Arka plan bakım: %d süresi dolmuş telemetry satırı silindi", deleted)
        except Exception:
            logger.exception("Arka plan bakım: telemetry temizliği başarısız oldu")
    finally:
        await conn.close()


async def run_agent_maintenance() -> None:
    """Sonsuz döngü — `app/main.py::lifespan` tarafından bir
    `asyncio.Task` olarak başlatılır, shutdown'da `task.cancel()` ile
    durdurulur (`CancelledError` burada YUTULMAZ)."""
    interval = _interval_seconds()
    logger.info("Arka plan Agent bakım worker'ı başlatıldı (interval=%ss)", interval)
    while True:
        await _run_once()
        await asyncio.sleep(interval)
