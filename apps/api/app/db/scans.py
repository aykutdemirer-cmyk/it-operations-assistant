from datetime import datetime
from pathlib import Path
from uuid import UUID

import asyncpg

from app.db.connection import DATABASE_URL

# Tek doğruluk kaynağı: infra/postgres/init.sql (assets.py ile aynı dosya —
# şema iki yerde tekrarlanmaz). scans tablosunda JSONB kolon olmadığı için
# assets.py'deki gibi bir jsonb codec'ine ihtiyaç yok.
_SCHEMA_SQL_PATH = Path(__file__).resolve().parents[4] / "infra" / "postgres" / "init.sql"
CREATE_SCANS_TABLE_SQL = _SCHEMA_SQL_PATH.read_text(encoding="utf-8")


async def get_connection() -> asyncpg.Connection:
    """`DATABASE_URL`'e bağlanır. `timeout=2`: PostgreSQL erişilemezken
    hızlı başarısız olmak için (bkz. `app/db/assets.py::get_connection`)."""
    return await asyncpg.connect(DATABASE_URL, timeout=2)


async def ensure_schema(conn: asyncpg.Connection) -> None:
    """`scans` tablosunu ve indexlerini yoksa oluşturur. Tekrar çağrılması
    güvenlidir. Dosya `assets` tablosunun DDL'ini de içerir — bu modülün
    `ensure_schema`'sını çağırmak `app/db/assets.py::ensure_schema`'yı
    çağırmakla aynı etkiyi yapar (ikisi de aynı idempotent SQL'i çalıştırır);
    hangisinin çağrıldığı önemli değildir."""
    await conn.execute(CREATE_SCANS_TABLE_SQL)


async def create_scan(conn: asyncpg.Connection, *, cidr: str, started_at: datetime) -> dict:
    """Bir tarama başlamadan önce `running` durumunda bir kayıt açar."""
    row = await conn.fetchrow(
        """
        INSERT INTO scans (cidr, started_at, status)
        VALUES ($1, $2, 'running')
        RETURNING *
        """,
        cidr,
        started_at,
    )
    return dict(row)


async def complete_scan(
    conn: asyncpg.Connection,
    *,
    scan_id: UUID,
    completed_at: datetime,
    duration_ms: float,
    hosts_scanned: int,
    hosts_discovered: int,
    open_ports: int,
) -> dict:
    """Bir taramayı istatistikleriyle birlikte `completed` olarak işaretler."""
    row = await conn.fetchrow(
        """
        UPDATE scans
        SET completed_at = $2,
            duration_ms = $3,
            hosts_scanned = $4,
            hosts_discovered = $5,
            open_ports = $6,
            status = 'completed'
        WHERE id = $1
        RETURNING *
        """,
        scan_id,
        completed_at,
        duration_ms,
        hosts_scanned,
        hosts_discovered,
        open_ports,
    )
    return dict(row)


async def fail_scan(
    conn: asyncpg.Connection, *, scan_id: UUID, completed_at: datetime, duration_ms: float
) -> dict:
    """Bir taramayı `failed` olarak işaretler (istatistikler bilinmediği
    için varsayılan 0 değerlerinde kalır)."""
    row = await conn.fetchrow(
        """
        UPDATE scans
        SET completed_at = $2,
            duration_ms = $3,
            status = 'failed'
        WHERE id = $1
        RETURNING *
        """,
        scan_id,
        completed_at,
        duration_ms,
    )
    return dict(row)


async def list_scans(conn: asyncpg.Connection) -> list[dict]:
    """Tüm taramaları `started_at DESC` (en son başlayan en üstte)
    sırayla döner. `list_assets` ile aynı imza — parametre yok, "son N"
    kısıtı frontend'de uygulanır."""
    rows = await conn.fetch("SELECT * FROM scans ORDER BY started_at DESC")
    return [dict(row) for row in rows]
