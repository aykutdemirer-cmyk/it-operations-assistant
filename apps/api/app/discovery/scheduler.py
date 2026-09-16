"""Faz 71 — Zamanlanmış Ağ Taraması arka plan worker'ı.

`app/snmp/scheduler.py`/`app/agents/scheduler.py` ile AYNI desen: sonsuz
döngü, sabit tick, bir turun/zamanlamanın hatası worker'ı ASLA
DURDURMAZ, `asyncio.CancelledError` yutulmaz.

**Güvenlik ilkesi (CLAUDE.md):** burada YENİ bir CIDR keşfedilmez ya da
taranmaz — yalnızca kullanıcının Ayarlar'da AÇIKÇA kaydettiği bir CIDR
periyodik olarak TEKRAR taranır, elle taramayla TAMAMEN aynı kod yolu
(`app/routes/discovery.py`'nin zaten "discovery↔DB tek temas noktası"
olarak belgeli yardımcıları) kullanılarak."""

import asyncio
import logging
import os
from datetime import datetime, timezone

from app.db import scheduled_scans as schedules_repo
from app.discovery.cidr import InvalidCIDRError
from app.discovery.scanner import scan_network
from app.routes.discovery import complete_scan_record, fail_scan_record, persist_scan_result, start_scan_record

logger = logging.getLogger(__name__)

_DEFAULT_TICK_SECONDS = 60


def is_discovery_scheduler_enabled() -> bool:
    raw = os.environ.get("DISCOVERY_SCHEDULER_ENABLED", "true")
    return raw.strip().lower() not in ("0", "false", "no")


def _tick_seconds() -> int:
    raw = os.environ.get("DISCOVERY_SCHEDULER_TICK_SECONDS")
    if not raw:
        return _DEFAULT_TICK_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_TICK_SECONDS
    return value if value > 0 else _DEFAULT_TICK_SECONDS


async def _run_schedule(schedule) -> None:
    """Tek bir zamanlamayı elle taramayla AYNI akışla çalıştırır. Hata
    diğer zamanlamaları ASLA etkilemez (`_run_once` her biri için ayrı
    yakalar)."""
    cidr = schedule["cidr"]
    started_at = datetime.now(timezone.utc)
    scan_id = await start_scan_record(cidr, started_at)

    try:
        result = await scan_network(cidr)
    except InvalidCIDRError as exc:
        await fail_scan_record(scan_id, started_at)
        raise
    except Exception:
        await fail_scan_record(scan_id, started_at)
        raise

    await persist_scan_result(result)
    await complete_scan_record(scan_id, started_at, result)


async def _run_once() -> None:
    try:
        conn = await schedules_repo.get_connection()
    except OSError:
        logger.warning("Zamanlanmış tarama turu atlandı — PostgreSQL erişilemedi")
        return

    try:
        due = await schedules_repo.list_due(conn)
    except Exception:
        logger.exception("Süresi gelen zamanlamalar okunamadı")
        await conn.close()
        return

    for schedule in due:
        ran_at = datetime.now(timezone.utc)
        try:
            await _run_schedule(schedule)
        except Exception as exc:
            logger.exception("Zamanlanmış tarama başarısız: cidr=%s", schedule["cidr"])
            try:
                await schedules_repo.record_run_result(conn, schedule["id"], ran_at=ran_at, status="error", error=str(exc))
            except Exception:
                logger.exception("Zamanlama sonucu kaydedilemedi: id=%s", schedule["id"])
            continue

        try:
            await schedules_repo.record_run_result(conn, schedule["id"], ran_at=ran_at, status="success", error=None)
            logger.info("Zamanlanmış tarama tamamlandı: cidr=%s", schedule["cidr"])
        except Exception:
            logger.exception("Zamanlama sonucu kaydedilemedi: id=%s", schedule["id"])

    await conn.close()


async def run_discovery_scheduler() -> None:
    tick = _tick_seconds()
    logger.info("Zamanlanmış tarama worker'ı başlatıldı (tick=%ss)", tick)
    while True:
        await _run_once()
        await asyncio.sleep(tick)
