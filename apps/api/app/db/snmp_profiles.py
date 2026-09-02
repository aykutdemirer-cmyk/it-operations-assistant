from datetime import datetime
from pathlib import Path
from uuid import UUID

import asyncpg

from app.db.connection import DATABASE_URL

# Tek doğruluk kaynağı: infra/postgres/init.sql (assets/scans/agents ile
# aynı dosya — şema hiçbir yerde tekrarlanmaz).
_SCHEMA_SQL_PATH = Path(__file__).resolve().parents[4] / "infra" / "postgres" / "init.sql"
CREATE_SNMP_PROFILES_TABLE_SQL = _SCHEMA_SQL_PATH.read_text(encoding="utf-8")

_INSERT_SQL = """
INSERT INTO snmp_profiles (
    name, target_host, port, version, timeout_seconds, retries, enabled,
    community_ref, username, auth_protocol, auth_credential_ref,
    priv_protocol, priv_credential_ref
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
RETURNING *;
"""

_UPDATE_SQL = """
UPDATE snmp_profiles SET
    name = $2, target_host = $3, port = $4, version = $5,
    timeout_seconds = $6, retries = $7, enabled = $8,
    community_ref = $9, username = $10, auth_protocol = $11,
    auth_credential_ref = $12, priv_protocol = $13, priv_credential_ref = $14,
    updated_at = clock_timestamp()
WHERE id = $1
RETURNING *;
"""


async def get_connection() -> asyncpg.Connection:
    """`DATABASE_URL`'e bağlanır. `snmp_profiles` tablosunda JSONB kolon
    yok — `app/db/scans.py::get_connection` ile aynı gerekçe, ayrı bir
    codec kaydı gerekmiyor."""
    return await asyncpg.connect(DATABASE_URL, timeout=2)


async def ensure_schema(conn: asyncpg.Connection) -> None:
    """`snmp_profiles` tablosunu ve indexlerini yoksa oluşturur. Tekrar
    çağrılması güvenlidir."""
    await conn.execute(CREATE_SNMP_PROFILES_TABLE_SQL)


async def insert_profile(
    conn: asyncpg.Connection,
    *,
    name: str,
    target_host: str,
    port: int,
    version: str,
    timeout_seconds: float,
    retries: int,
    enabled: bool,
    community_ref: str | None,
    username: str | None,
    auth_protocol: str | None,
    auth_credential_ref: str | None,
    priv_protocol: str | None,
    priv_credential_ref: str | None,
) -> dict:
    row = await conn.fetchrow(
        _INSERT_SQL,
        name, target_host, port, version, timeout_seconds, retries, enabled,
        community_ref, username, auth_protocol, auth_credential_ref,
        priv_protocol, priv_credential_ref,
    )
    return dict(row)


async def update_profile(
    conn: asyncpg.Connection,
    *,
    profile_id: UUID,
    name: str,
    target_host: str,
    port: int,
    version: str,
    timeout_seconds: float,
    retries: int,
    enabled: bool,
    community_ref: str | None,
    username: str | None,
    auth_protocol: str | None,
    auth_credential_ref: str | None,
    priv_protocol: str | None,
    priv_credential_ref: str | None,
) -> dict | None:
    row = await conn.fetchrow(
        _UPDATE_SQL,
        profile_id, name, target_host, port, version, timeout_seconds, retries,
        enabled, community_ref, username, auth_protocol, auth_credential_ref,
        priv_protocol, priv_credential_ref,
    )
    return dict(row) if row else None


async def get_profile_by_id(conn: asyncpg.Connection, profile_id: UUID) -> dict | None:
    row = await conn.fetchrow("SELECT * FROM snmp_profiles WHERE id = $1", profile_id)
    return dict(row) if row else None


async def list_profiles(conn: asyncpg.Connection) -> list[dict]:
    """Tüm profilleri `name` sırayla döner (NOC/config listeleri için
    alfabetik sıralama, zaman bazlı değil — `assets`/`scans`'tan farklı
    olarak burada 'en yeni üstte' anlamlı değil)."""
    rows = await conn.fetch("SELECT * FROM snmp_profiles ORDER BY name")
    return [dict(row) for row in rows]


async def get_enabled_profile_by_target_host(conn: asyncpg.Connection, target_host: str) -> dict | None:
    """Faz 30+ (poller entegrasyonu) için hazırlanan sorgu — bir asset'in
    IP'sine karşılık gelen, etkin bir profil var mı diye bakar. Bu faz
    henüz `profile_store.py`'yi buna bağlamıyor (bkz. docs/decisions.md
    §10.3'ün "sonraki adım" notu)."""
    row = await conn.fetchrow(
        "SELECT * FROM snmp_profiles WHERE target_host = $1 AND enabled = true", target_host
    )
    return dict(row) if row else None


async def delete_profile(conn: asyncpg.Connection, profile_id: UUID) -> bool:
    result = await conn.execute("DELETE FROM snmp_profiles WHERE id = $1", profile_id)
    return result == "DELETE 1"
