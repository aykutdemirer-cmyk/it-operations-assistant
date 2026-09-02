import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

import asyncpg

from app.db.connection import DATABASE_URL

# Tek doğruluk kaynağı: infra/postgres/init.sql (assets/scans ile aynı
# dosya — şema hiçbir yerde tekrarlanmaz).
_SCHEMA_SQL_PATH = Path(__file__).resolve().parents[4] / "infra" / "postgres" / "init.sql"
CREATE_AGENTS_TABLES_SQL = _SCHEMA_SQL_PATH.read_text(encoding="utf-8")

_INSERT_AGENT_SQL = """
INSERT INTO agents (
    hostname, fqdn, os, os_version, architecture, agent_version, local_ip,
    mac_address, capabilities, token_hash
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
RETURNING *;
"""

_UPSERT_TELEMETRY_SQL = """
INSERT INTO agent_telemetry (
    agent_id, collected_at, cpu_percent, memory_total_bytes,
    memory_used_bytes, memory_percent, disks, network_interfaces,
    sessions_json, last_logged_in_user, active_sessions_count
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
RETURNING *;
"""

_UPSERT_INVENTORY_SQL = """
INSERT INTO agent_inventory (
    agent_id, hardware, os, network_interfaces, software, services,
    processes, collected_at
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (agent_id) DO UPDATE SET
    hardware = EXCLUDED.hardware,
    os = EXCLUDED.os,
    network_interfaces = EXCLUDED.network_interfaces,
    software = EXCLUDED.software,
    services = EXCLUDED.services,
    processes = EXCLUDED.processes,
    collected_at = EXCLUDED.collected_at,
    updated_at = clock_timestamp()
RETURNING *;
"""


async def get_connection() -> asyncpg.Connection:
    """`DATABASE_URL`'e bağlanır ve jsonb codec'ini kaydeder (`agents.
    capabilities`, `agent_telemetry.disks`/`network_interfaces`,
    `agent_inventory.*` alanları için — bkz. `app/db/assets.py::
    get_connection`, aynı gerekçe)."""
    conn = await asyncpg.connect(DATABASE_URL, timeout=2)
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    return conn


async def ensure_schema(conn: asyncpg.Connection) -> None:
    """`agents`/`agent_telemetry`/`agent_inventory` tablolarını yoksa
    oluşturur. Tekrar çağrılması güvenlidir."""
    await conn.execute(CREATE_AGENTS_TABLES_SQL)


async def insert_agent(
    conn: asyncpg.Connection,
    *,
    hostname: str,
    os: str,
    os_version: str | None,
    architecture: str | None,
    agent_version: str,
    local_ip: str | None,
    mac_address: str | None,
    capabilities: list[str],
    token_hash: str,
    fqdn: str | None = None,
) -> dict:
    row = await conn.fetchrow(
        _INSERT_AGENT_SQL,
        hostname, fqdn, os, os_version, architecture, agent_version, local_ip,
        mac_address, capabilities, token_hash,
    )
    return dict(row)


async def get_agent_by_id(conn: asyncpg.Connection, agent_id: UUID) -> dict | None:
    row = await conn.fetchrow("SELECT * FROM agents WHERE id = $1", agent_id)
    return dict(row) if row else None


async def get_agent_by_token_hash(conn: asyncpg.Connection, token_hash: str) -> dict | None:
    row = await conn.fetchrow("SELECT * FROM agents WHERE token_hash = $1", token_hash)
    return dict(row) if row else None


async def set_agent_asset_id(
    conn: asyncpg.Connection, *, agent_id: UUID, asset_id: UUID | None
) -> dict | None:
    """`agents.asset_id`'yi AÇIKÇA ayarlar — yalnızca `app/agents/
    service.py::confirm_agent_asset_match` (insan onaylı bir eşleştirme
    sonrası) tarafından çağrılır; hiçbir otomatik/arka plan süreci bu
    fonksiyonu kendiliğinden çağırmaz (bkz. `app/agents/matching.py`)."""
    row = await conn.fetchrow(
        "UPDATE agents SET asset_id = $2 WHERE id = $1 RETURNING *;", agent_id, asset_id
    )
    return dict(row) if row else None


async def list_agents(conn: asyncpg.Connection) -> list[dict]:
    """Tüm agent'ları `registered_at DESC` sırayla döner."""
    rows = await conn.fetch("SELECT * FROM agents ORDER BY registered_at DESC")
    return [dict(row) for row in rows]


async def update_heartbeat(
    conn: asyncpg.Connection,
    *,
    agent_id: UUID,
    heartbeat_at: datetime,
    uptime_seconds: float | None,
    agent_version: str | None,
) -> dict | None:
    """`agent_version` verilmişse (agent kendini güncellemiş olabilir)
    kayıt güncellenir; verilmemişse mevcut değer korunur (COALESCE)."""
    row = await conn.fetchrow(
        """
        UPDATE agents SET
            last_heartbeat_at = $2,
            last_heartbeat_uptime_seconds = $3,
            agent_version = COALESCE($4, agent_version)
        WHERE id = $1
        RETURNING *;
        """,
        agent_id, heartbeat_at, uptime_seconds, agent_version,
    )
    return dict(row) if row else None


async def insert_telemetry(
    conn: asyncpg.Connection,
    *,
    agent_id: UUID,
    collected_at: datetime,
    cpu_percent: float | None,
    memory_total_bytes: int | None,
    memory_used_bytes: int | None,
    memory_percent: float | None,
    disks: list[dict],
    network_interfaces: list[dict],
    sessions: list[dict] | None = None,
    last_logged_in_user: str | None = None,
    active_sessions_count: int | None = None,
) -> dict:
    row = await conn.fetchrow(
        _UPSERT_TELEMETRY_SQL,
        agent_id, collected_at, cpu_percent, memory_total_bytes,
        memory_used_bytes, memory_percent, disks, network_interfaces,
        sessions or [], last_logged_in_user, active_sessions_count,
    )
    return dict(row)


async def get_latest_telemetry(conn: asyncpg.Connection, agent_id: UUID) -> dict | None:
    row = await conn.fetchrow(
        "SELECT * FROM agent_telemetry WHERE agent_id = $1 ORDER BY collected_at DESC LIMIT 1",
        agent_id,
    )
    return dict(row) if row else None


async def upsert_inventory(
    conn: asyncpg.Connection,
    *,
    agent_id: UUID,
    hardware: dict | None,
    os: dict | None,
    network_interfaces: list[dict],
    software: list[dict],
    services: list[dict],
    processes: list[dict],
    collected_at: datetime,
) -> dict:
    row = await conn.fetchrow(
        _UPSERT_INVENTORY_SQL,
        agent_id, hardware, os, network_interfaces, software, services, processes, collected_at,
    )
    return dict(row)


async def get_inventory(conn: asyncpg.Connection, agent_id: UUID) -> dict | None:
    row = await conn.fetchrow("SELECT * FROM agent_inventory WHERE agent_id = $1", agent_id)
    return dict(row) if row else None


async def delete_expired_telemetry(conn: asyncpg.Connection, retention_days: int) -> int:
    """`agent_telemetry`'den `retention_days`'ten eski satırları siler —
    idempotent (tekrar çalıştırmak güvenli, ikinci çalıştırma 0 satır
    siler; bkz. Faz 29 karar — `docs/decisions.md`). Şu an hiçbir
    zamanlayıcı tarafından otomatik ÇAĞRILMIYOR (Faz 38 Scheduler'ın
    kapsamı) — bu fonksiyon manuel/gelecekteki zamanlanmış çağrı için
    hazır, test edilmiş bir yapı taşı."""
    if retention_days <= 0:
        raise ValueError("retention_days pozitif olmalı")
    result = await conn.execute(
        "DELETE FROM agent_telemetry WHERE collected_at < now() - ($1 || ' days')::interval",
        str(retention_days),
    )
    # asyncpg execute() "DELETE <n>" formatında bir string döner.
    try:
        return int(result.split(" ")[1])
    except (IndexError, ValueError):
        return 0
