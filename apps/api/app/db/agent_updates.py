"""`agent_windows_updates` tablosu için ham SQL — `app/db/agent_
commands.py` ile AYNI "her yeni özellik kendi dosyasında" ilkesiyle
ayrı tutuldu (bkz. CLAUDE.md). Agent başına TEK satır (`agent_
inventory` ile AYNI "şu anki durum, tarihçe yok" deseni)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

_UPSERT_SQL = """
INSERT INTO agent_windows_updates (
    agent_id, collected_at, scan_method, is_admin, updates, error, reboot_required
) VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (agent_id) DO UPDATE SET
    collected_at = EXCLUDED.collected_at,
    scan_method = EXCLUDED.scan_method,
    is_admin = EXCLUDED.is_admin,
    updates = EXCLUDED.updates,
    error = EXCLUDED.error,
    reboot_required = EXCLUDED.reboot_required,
    updated_at = clock_timestamp()
RETURNING *;
"""


async def upsert_scan_result(
    conn: asyncpg.Connection,
    *,
    agent_id: UUID,
    collected_at: datetime,
    scan_method: str,
    is_admin: bool,
    updates: list[dict],
    error: str | None,
    reboot_required: bool = False,
) -> dict:
    row = await conn.fetchrow(
        _UPSERT_SQL, agent_id, collected_at, scan_method, is_admin, updates, error, reboot_required
    )
    return dict(row)


async def get_scan_result(conn: asyncpg.Connection, agent_id: UUID) -> dict | None:
    row = await conn.fetchrow("SELECT * FROM agent_windows_updates WHERE agent_id = $1", agent_id)
    return dict(row) if row else None
