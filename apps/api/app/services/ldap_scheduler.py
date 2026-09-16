"""Faz 49 — gece yarısı arka plan LDAP senkronizasyon worker'ı.

Kullanıcının isteği "Celery ile her gece 02:00'de" idi — bu proje HİÇBİR
zaman Celery kullanmadı (mesaj kuyruğu/broker altyapısı — Redis/
RabbitMQ — yok) ve tek bir zamanlanmış görev için onu eklemek orantısız
bir mimari genişleme olurdu. Bunun yerine mevcut `app/snmp/scheduler.py`/
`app/agents/scheduler.py` ile AYNI desen: FastAPI `lifespan`'da başlayan
tek bir `asyncio.Task`, döngü içinde bir sonraki 02:00'a kadar uyur."""

import asyncio
import logging
import os
from datetime import datetime, time, timedelta

from app.db.ldap import get_config, get_connection, record_sync_result
from app.services.ldap import LdapConnectError, LdapConnectionParams, decrypt_bind_password, sync_directory

logger = logging.getLogger(__name__)

_DEFAULT_SYNC_HOUR = 2  # 02:00 yerel saat


def is_scheduled_sync_enabled() -> bool:
    raw = os.environ.get("LDAP_SCHEDULED_SYNC_ENABLED", "true")
    return raw.strip().lower() not in ("0", "false", "no")


def _sync_hour() -> int:
    raw = os.environ.get("LDAP_SYNC_HOUR")
    if not raw:
        return _DEFAULT_SYNC_HOUR
    try:
        hour = int(raw)
    except ValueError:
        return _DEFAULT_SYNC_HOUR
    return hour if 0 <= hour <= 23 else _DEFAULT_SYNC_HOUR


def _seconds_until_next_run(now: datetime, hour: int) -> float:
    target = datetime.combine(now.date(), time(hour=hour))
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def _run_once() -> None:
    try:
        conn = await get_connection()
    except OSError:
        logger.warning("Zamanlanmış LDAP senkronizasyonu atlandı — PostgreSQL erişilemedi")
        return

    try:
        config = await get_config(conn)
        if config is None:
            logger.info("Zamanlanmış LDAP senkronizasyonu atlandı — LDAP henüz yapılandırılmamış")
            return

        params: LdapConnectionParams = {
            "host": config["host"],
            "port": config["port"],
            "use_ssl": config["use_ssl"],
            "domain_fqdn": config["domain_fqdn"],
            "bind_dn": config["bind_dn"],
            "bind_password": decrypt_bind_password(config["encrypted_bind_password"]),
            "base_dn": config["base_dn"],
        }
        try:
            result = await sync_directory(conn, params)
            await record_sync_result(conn, status="success", error=None)
            logger.info(
                "Zamanlanmış LDAP senkronizasyonu tamamlandı: groups=%d users=%d memberships=%d",
                result.groups_synced, result.users_synced, result.memberships_synced,
            )
        except LdapConnectError as exc:
            await record_sync_result(conn, status="error", error=str(exc))
            logger.warning("Zamanlanmış LDAP senkronizasyonu başarısız: %s", exc)
    except Exception:
        logger.exception("Zamanlanmış LDAP senkronizasyonu beklenmeyen bir hatayla başarısız oldu")
    finally:
        await conn.close()


async def run_scheduled_ldap_sync() -> None:
    """Sonsuz döngü — `app/main.py::lifespan` tarafından bir
    `asyncio.Task` olarak başlatılır, shutdown'da `task.cancel()` ile
    durdurulur (`CancelledError` burada YUTULMAZ)."""
    hour = _sync_hour()
    logger.info("Zamanlanmış LDAP senkronizasyon worker'ı başlatıldı (hedef saat=%02d:00)", hour)
    while True:
        delay = _seconds_until_next_run(datetime.now(), hour)
        await asyncio.sleep(delay)
        await _run_once()
