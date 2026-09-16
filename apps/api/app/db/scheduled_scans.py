"""Faz 71 — `scheduled_scans` DB katmanı. Kullanıcının Ayarlar'da
açıkça kaydettiği bir CIDR'ın periyodik yeniden taranması için."""

from datetime import datetime
from uuid import UUID

import asyncpg

from app.db.connection import DATABASE_URL


async def get_connection() -> asyncpg.Connection:
    return await asyncpg.connect(DATABASE_URL, timeout=2)


async def list_schedules(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch("SELECT * FROM scheduled_scans ORDER BY created_at ASC")


async def get_schedule(conn: asyncpg.Connection, schedule_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM scheduled_scans WHERE id = $1", schedule_id)


async def insert_schedule(conn: asyncpg.Connection, *, cidr: str, interval_hours: int, enabled: bool) -> asyncpg.Record:
    return await conn.fetchrow(
        """
        INSERT INTO scheduled_scans (cidr, interval_hours, enabled)
        VALUES ($1, $2, $3)
        RETURNING *;
        """,
        cidr,
        interval_hours,
        enabled,
    )


async def update_schedule(
    conn: asyncpg.Connection,
    schedule_id: UUID,
    *,
    cidr: str | None,
    interval_hours: int | None,
    enabled: bool | None,
    _unset: set[str],
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        UPDATE scheduled_scans SET
            cidr = CASE WHEN $2 THEN $3 ELSE cidr END,
            interval_hours = CASE WHEN $4 THEN $5 ELSE interval_hours END,
            enabled = CASE WHEN $6 THEN $7 ELSE enabled END,
            updated_at = clock_timestamp()
        WHERE id = $1
        RETURNING *;
        """,
        schedule_id,
        "cidr" in _unset,
        cidr,
        "interval_hours" in _unset,
        interval_hours,
        "enabled" in _unset,
        enabled,
    )


async def delete_schedule(conn: asyncpg.Connection, schedule_id: UUID) -> bool:
    result = await conn.execute("DELETE FROM scheduled_scans WHERE id = $1", schedule_id)
    return result.endswith(" 1")


async def list_due(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    """`enabled` VE (hiç çalışmamış YA DA son çalışmadan bu yana
    `interval_hours` saat geçmiş) zamanlamalar."""
    return await conn.fetch(
        """
        SELECT * FROM scheduled_scans
        WHERE enabled = true
          AND (last_run_at IS NULL OR last_run_at + (interval_hours || ' hours')::interval <= now())
        ORDER BY last_run_at ASC NULLS FIRST;
        """
    )


async def record_run_result(
    conn: asyncpg.Connection, schedule_id: UUID, *, ran_at: datetime, status: str, error: str | None
) -> None:
    if error is not None:
        error = error.replace("\x00", "")
    await conn.execute(
        """
        UPDATE scheduled_scans
        SET last_run_at = $2, last_run_status = $3, last_run_error = $4, updated_at = clock_timestamp()
        WHERE id = $1;
        """,
        schedule_id,
        ran_at,
        status,
        error,
    )
