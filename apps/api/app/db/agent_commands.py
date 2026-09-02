from datetime import datetime
from pathlib import Path
from uuid import UUID

import asyncpg

from app.db.connection import DATABASE_URL

# Tek doğruluk kaynağı: infra/postgres/init.sql (bkz. app/db/scans.py'deki
# aynı desen — dosya TÜM tabloların DDL'ini içerir, hangi modülün
# ensure_schema'sı çağrılırsa çağrılsın aynı idempotent SQL çalışır).
_SCHEMA_SQL_PATH = Path(__file__).resolve().parents[4] / "infra" / "postgres" / "init.sql"
CREATE_AGENT_COMMANDS_TABLE_SQL = _SCHEMA_SQL_PATH.read_text(encoding="utf-8")


async def get_connection() -> asyncpg.Connection:
    return await asyncpg.connect(DATABASE_URL, timeout=2)


async def ensure_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(CREATE_AGENT_COMMANDS_TABLE_SQL)


async def create_command(
    conn: asyncpg.Connection,
    *,
    agent_id: UUID,
    command_type: str,
    action: str,
    target: str,
    requested_by: str | None,
) -> dict:
    """Yeni bir komut `pending` durumunda oluşturur — Agent'ın
    command-poll döngüsü bunu bir sonraki turunda çeker (bkz.
    `list_pending_and_mark_sent`)."""
    row = await conn.fetchrow(
        """
        INSERT INTO agent_commands (agent_id, command_type, action, target, requested_by)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        agent_id,
        command_type,
        action,
        target,
        requested_by,
    )
    return dict(row)


async def create_rejected_command(
    conn: asyncpg.Connection,
    *,
    agent_id: UUID,
    command_type: str,
    action: str,
    target: str,
    requested_by: str | None,
    reason: str,
) -> dict:
    """Backend'in kendi (koarse) reddi için — ör. PID <= 4. Agent'a hiç
    gönderilmez ama audit izinde 'reddedildi' olarak görünür kalır."""
    row = await conn.fetchrow(
        """
        INSERT INTO agent_commands
            (agent_id, command_type, action, target, requested_by, status, result_detail, completed_at)
        VALUES ($1, $2, $3, $4, $5, 'rejected', $6, now())
        RETURNING *
        """,
        agent_id,
        command_type,
        action,
        target,
        requested_by,
        reason,
    )
    return dict(row)


async def list_commands_for_agent(conn: asyncpg.Connection, agent_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        "SELECT * FROM agent_commands WHERE agent_id = $1 ORDER BY created_at DESC LIMIT 100",
        agent_id,
    )
    return [dict(row) for row in rows]


async def get_command(conn: asyncpg.Connection, command_id: UUID) -> dict | None:
    row = await conn.fetchrow("SELECT * FROM agent_commands WHERE id = $1", command_id)
    return dict(row) if row else None


async def list_pending_and_mark_sent(conn: asyncpg.Connection, agent_id: UUID) -> list[dict]:
    """Bekleyen komutları döner VE aynı anda `sent`e işaretler (tek
    UPDATE...RETURNING — agent iki kere aynı komutu çekip iki kere
    çalıştırmasın diye, bkz. `docs/decisions.md` §17)."""
    rows = await conn.fetch(
        """
        UPDATE agent_commands
        SET status = 'sent', sent_at = now()
        WHERE agent_id = $1 AND status = 'pending'
        RETURNING *
        """,
        agent_id,
    )
    return [dict(row) for row in rows]


async def complete_command(
    conn: asyncpg.Connection, *, command_id: UUID, status: str, result_detail: str | None
) -> dict | None:
    row = await conn.fetchrow(
        """
        UPDATE agent_commands
        SET status = $2, result_detail = $3, completed_at = now()
        WHERE id = $1
        RETURNING *
        """,
        command_id,
        status,
        result_detail,
    )
    return dict(row) if row else None
