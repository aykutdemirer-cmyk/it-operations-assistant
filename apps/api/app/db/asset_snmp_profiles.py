from datetime import datetime
from pathlib import Path
from uuid import UUID

import asyncpg

from app.db.connection import DATABASE_URL

# Tek doğruluk kaynağı: infra/postgres/init.sql (diğer tüm tablolarla
# aynı dosya — şema hiçbir yerde tekrarlanmaz).
_SCHEMA_SQL_PATH = Path(__file__).resolve().parents[4] / "infra" / "postgres" / "init.sql"
CREATE_ASSET_SNMP_PROFILES_TABLE_SQL = _SCHEMA_SQL_PATH.read_text(encoding="utf-8")

_ASSIGN_SQL = """
INSERT INTO asset_snmp_profiles (asset_id, snmp_profile_id)
VALUES ($1, $2)
ON CONFLICT (asset_id) DO UPDATE SET
    snmp_profile_id = EXCLUDED.snmp_profile_id,
    updated_at = clock_timestamp()
RETURNING *;
"""

_PROFILE_FOR_ASSET_SQL = """
SELECT sp.*, asp.created_at AS assigned_at, asp.updated_at AS assignment_updated_at
FROM asset_snmp_profiles asp
JOIN snmp_profiles sp ON sp.id = asp.snmp_profile_id
WHERE asp.asset_id = $1;
"""

_ASSETS_FOR_PROFILE_SQL = """
SELECT a.*
FROM asset_snmp_profiles asp
JOIN assets a ON a.id = asp.asset_id
WHERE asp.snmp_profile_id = $1
ORDER BY a.ip_address;
"""


async def get_connection() -> asyncpg.Connection:
    """`DATABASE_URL`'e bağlanır. `asset_snmp_profiles`'ta JSONB kolon
    yok — ayrı bir codec kaydına gerek yok (bkz. `app/db/scans.py::
    get_connection`, aynı gerekçe)."""
    return await asyncpg.connect(DATABASE_URL, timeout=2)


async def ensure_schema(conn: asyncpg.Connection) -> None:
    """`asset_snmp_profiles` tablosunu (ve şemadaki her şeyi) yoksa
    oluşturur. Tekrar çağrılması güvenlidir."""
    await conn.execute(CREATE_ASSET_SNMP_PROFILES_TABLE_SQL)


async def assign_profile_to_asset(
    conn: asyncpg.Connection, *, asset_id: UUID, profile_id: UUID
) -> dict:
    """Bir asset'e bir profil atar. Asset'in zaten bir ataması varsa
    ÜZERİNE YAZAR (upsert, `ON CONFLICT (asset_id)`) — bu, "reassign"
    akışının kendisidir, ayrı bir fonksiyon gerekmez. Foreign key
    kontrolü (asset/profile gerçekten var mı) ÇAĞIRAN TARAFIN
    sorumluluğu (bkz. `app/snmp/asset_profile_service.py`) — burada
    yalnızca ham SQL çalıştırılır."""
    row = await conn.fetchrow(_ASSIGN_SQL, asset_id, profile_id)
    return dict(row)


async def unassign_profile_from_asset(conn: asyncpg.Connection, asset_id: UUID) -> bool:
    result = await conn.execute(
        "DELETE FROM asset_snmp_profiles WHERE asset_id = $1", asset_id
    )
    return result == "DELETE 1"


async def get_profile_for_asset(conn: asyncpg.Connection, asset_id: UUID) -> dict | None:
    """Bir asset'e atanmış profili (varsa) `snmp_profiles`'ın TÜM
    sütunlarıyla birlikte döner — `assigned_at`/`assignment_updated_at`
    ek alanları atama kaydının kendi zaman damgalarıdır."""
    row = await conn.fetchrow(_PROFILE_FOR_ASSET_SQL, asset_id)
    return dict(row) if row else None


async def list_assets_for_profile(conn: asyncpg.Connection, profile_id: UUID) -> list[dict]:
    """Bir profile atanmış TÜM asset satırlarını (tam `assets` şeması)
    IP sırasıyla döner."""
    rows = await conn.fetch(_ASSETS_FOR_PROFILE_SQL, profile_id)
    return [dict(row) for row in rows]


async def count_assets_for_profile(conn: asyncpg.Connection, profile_id: UUID) -> int:
    return await conn.fetchval(
        "SELECT count(*) FROM asset_snmp_profiles WHERE snmp_profile_id = $1", profile_id
    )


async def count_assets_by_profile(conn: asyncpg.Connection) -> dict[UUID, int]:
    """TÜM profillerin atanmış-asset sayısını TEK sorguda döner (Settings
    UI'daki profil listesinde N+1 sorgu yapmamak için)."""
    rows = await conn.fetch(
        "SELECT snmp_profile_id, count(*) AS n FROM asset_snmp_profiles GROUP BY snmp_profile_id"
    )
    return {row["snmp_profile_id"]: row["n"] for row in rows}
