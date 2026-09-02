import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

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
    status, latency_ms, open_ports, evidence, last_seen
) VALUES (
    $1::inet, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
)
ON CONFLICT (ip_address) DO UPDATE SET
    hostname = COALESCE(EXCLUDED.hostname, assets.hostname),
    mac_address = COALESCE(EXCLUDED.mac_address, assets.mac_address),
    vendor = COALESCE(EXCLUDED.vendor, assets.vendor),
    device_type = EXCLUDED.device_type,
    confidence = EXCLUDED.confidence,
    status = EXCLUDED.status,
    latency_ms = EXCLUDED.latency_ms,
    open_ports = EXCLUDED.open_ports,
    evidence = EXCLUDED.evidence,
    last_seen = EXCLUDED.last_seen,
    updated_at = clock_timestamp()
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
    latency_ms: float | None = None,
) -> dict:
    """Bir discovery sonucunu `assets` tablosuna yazar. IP, cihazın ana
    kimliğidir: zaten kayıtlıysa günceller (upsert), yeni bir satır
    oluşturmaz (`ip_address` UNIQUE + `ON CONFLICT (ip_address) DO
    UPDATE`).

    NULL alan davranışı — iki farklı kategori, bilinçli olarak ayrı ele
    alınır:
    - Kimlik alanları (`hostname`, `mac_address`, `vendor`): bu taramada
      `None` geldiyse mevcut değer korunur (COALESCE). Bunlar cihazın
      nispeten kalıcı özellikleridir; DNS/ARP geçici olarak
      çözülemedi diye daha önce bilinen değer silinmemeli.
    - Gözlem alanları (`status`, `latency_ms`, `open_ports`, `evidence`,
      `device_type`, `confidence`, `last_seen`): her taramada, `None`
      olsa bile yeni değerle DEĞİŞTİRİLİR. Bunlar "şu an" durumunu
      temsil eder — örn. host artık `down` ise `latency_ms`'in eski
      (host `up` iken ölçülmüş) değerini göstermeye devam etmesi yanlış
      bilgi verir.

    `created_at` yalnızca ilk eklemede ayarlanır, güncellemede hiç
    değişmez. `updated_at` için `now()` DEĞİL `clock_timestamp()`
    kullanılır: `now()` bir transaction boyunca sabit kalır (transaction
    başlangıç zamanı), bu yüzden aynı transaction içinde art arda iki
    upsert farklı `updated_at` üretmez. `clock_timestamp()` gerçek
    duvar-saati zamanını döner; her ayrı upsert (production'da normal
    kullanımda zaten ayrı transaction'lardır) kendi gerçek zamanını
    alır."""
    row = await conn.fetchrow(
        _UPSERT_ASSET_SQL,
        ip_address,
        hostname,
        mac_address,
        vendor,
        device_type,
        confidence,
        status,
        latency_ms,
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


async def get_asset_by_id(conn: asyncpg.Connection, asset_id: UUID) -> dict | None:
    row = await conn.fetchrow("SELECT * FROM assets WHERE id = $1", asset_id)
    return dict(row) if row else None


async def list_assets(conn: asyncpg.Connection) -> list[dict]:
    """Tüm asset'leri `last_seen DESC` (en son görülen en üstte) sırayla
    döner. Kullanıcıdan gelen bir girdi almadığı için parametreli bir
    değere ihtiyaç yok, ama sorgu yine de sabit bir string'dir — hiçbir
    değer SQL'e concatenate edilmez."""
    rows = await conn.fetch("SELECT * FROM assets ORDER BY last_seen DESC")
    return [dict(row) for row in rows]
