import json
from datetime import datetime
from pathlib import Path

import asyncpg

from app.db.connection import DATABASE_URL

# Tek doğruluk kaynağı: infra/postgres/init.sql. Bu dosya hem Docker init
# script'i olarak hem de burada runtime'da okunup çalıştırılmak üzere
# kullanılır — şema iki yerde tekrarlanmaz.
_SCHEMA_SQL_PATH = Path(__file__).resolve().parents[4] / "infra" / "postgres" / "init.sql"
CREATE_ASSETS_TABLE_SQL = _SCHEMA_SQL_PATH.read_text(encoding="utf-8")

_UPSERT_ASSET_SQL = """
INSERT INTO assets (
    ip_address, hostname, mac_address, vendor, device_type, confidence,
    status, open_ports, evidence, last_seen
) VALUES (
    $1::inet, $2, $3, $4, $5, $6, $7, $8, $9, $10
)
ON CONFLICT (ip_address) DO UPDATE SET
    hostname = COALESCE(EXCLUDED.hostname, assets.hostname),
    mac_address = COALESCE(EXCLUDED.mac_address, assets.mac_address),
    vendor = COALESCE(EXCLUDED.vendor, assets.vendor),
    device_type = EXCLUDED.device_type,
    confidence = EXCLUDED.confidence,
    status = EXCLUDED.status,
    open_ports = EXCLUDED.open_ports,
    evidence = EXCLUDED.evidence,
    last_seen = EXCLUDED.last_seen,
    updated_at = now()
RETURNING *;
"""


async def get_connection() -> asyncpg.Connection:
    """`DATABASE_URL`'e bağlanır ve jsonb codec'ini kaydeder (open_ports/
    evidence alanlarının Python list <-> JSONB arasında otomatik
    dönüşümü için, elle `json.dumps`/`json.loads` gerekmeden).

    `timeout=2`: PostgreSQL erişilemezken (örn. testlerde) hızlı
    başarısız olmak için — gerçek bir bağlantı için fazlasıyla yeterli."""
    conn = await asyncpg.connect(DATABASE_URL, timeout=2)
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    return conn


async def ensure_schema(conn: asyncpg.Connection) -> None:
    """`assets` tablosunu ve indexlerini yoksa oluşturur. Tekrar
    çağrılması güvenlidir (`CREATE TABLE`/`INDEX IF NOT EXISTS`)."""
    await conn.execute(CREATE_ASSETS_TABLE_SQL)


async def upsert_asset(
    conn: asyncpg.Connection,
    *,
    ip_address: str,
    hostname: str | None,
    mac_address: str | None,
    vendor: str | None,
    device_type: str,
    confidence: str,
    status: str,
    open_ports: list[dict],
    evidence: list[str],
    last_seen: datetime,
) -> dict:
    """Bir discovery sonucunu `assets` tablosuna yazar. IP zaten
    kayıtlıysa günceller (upsert); yeni bir satır oluşturmaz (IP unique).

    `hostname`/`mac_address`/`vendor` bu taramada `None` geldiyse mevcut
    değer korunur — bir cihazın önceki taramada bulunan bilgisi, sonraki
    bir taramada geçici olarak bulunamadı diye silinmez. `status`,
    `open_ports`, `evidence`, `device_type`, `confidence`, `last_seen`
    her taramada güncel değerle değiştirilir. `created_at` yalnızca ilk
    eklemede ayarlanır, güncellemede hiç değişmez."""
    row = await conn.fetchrow(
        _UPSERT_ASSET_SQL,
        ip_address,
        hostname,
        mac_address,
        vendor,
        device_type,
        confidence,
        status,
        open_ports,
        evidence,
        last_seen,
    )
    return dict(row)


async def get_asset_by_ip(conn: asyncpg.Connection, ip_address: str) -> dict | None:
    row = await conn.fetchrow(
        "SELECT * FROM assets WHERE ip_address = $1::inet", ip_address
    )
    return dict(row) if row else None
