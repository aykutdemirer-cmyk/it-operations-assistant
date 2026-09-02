from datetime import datetime
from pathlib import Path
from uuid import UUID

import asyncpg

from app.db.connection import DATABASE_URL

# Tek doğruluk kaynağı: infra/postgres/init.sql (agents/scans ile aynı
# dosya — şema hiçbir yerde tekrarlanmaz).
_SCHEMA_SQL_PATH = Path(__file__).resolve().parents[4] / "infra" / "postgres" / "init.sql"
CREATE_ENROLLMENT_CODES_TABLE_SQL = _SCHEMA_SQL_PATH.read_text(encoding="utf-8")

_INSERT_SQL = """
INSERT INTO agent_enrollment_codes (code, expires_at)
VALUES ($1, $2)
RETURNING *;
"""

_CONSUME_SQL = """
UPDATE agent_enrollment_codes
SET used_at = now()
WHERE code = $1 AND used_at IS NULL
RETURNING *;
"""


async def get_connection() -> asyncpg.Connection:
    return await asyncpg.connect(DATABASE_URL, timeout=2)


async def ensure_schema(conn: asyncpg.Connection) -> None:
    """`agent_enrollment_codes` tablosunu yoksa oluşturur. Tekrar
    çağrılması güvenlidir."""
    await conn.execute(CREATE_ENROLLMENT_CODES_TABLE_SQL)


async def insert_code(conn: asyncpg.Connection, *, code: str, expires_at: datetime) -> dict:
    row = await conn.fetchrow(_INSERT_SQL, code, expires_at)
    return dict(row)


async def get_code(conn: asyncpg.Connection, code: str) -> dict | None:
    row = await conn.fetchrow("SELECT * FROM agent_enrollment_codes WHERE code = $1", code)
    return dict(row) if row else None


async def consume_code(conn: asyncpg.Connection, code: str) -> dict | None:
    """`used_at`'i şimdiki zamana ayarlar — YALNIZCA henüz kullanılmamış
    bir kod için satır döner (`WHERE used_at IS NULL`); zaten
    kullanılmışsa `None` döner (tek kullanımlık garanti burada, tek bir
    atomik `UPDATE` ile — önce SELECT sonra UPDATE yapılmaz, bu yüzden
    iki eşzamanlı isteğin AYNI kodu tüketmesi mümkün değildir).
    `used_by_agent_id` burada henüz YOK — bu adımda agent henüz
    oluşturulmadı (bkz. `link_code_to_agent`, `register_agent`'ın
    çağırma sırası: önce kod tüketilir, SONRA agent oluşturulur, EN SON
    bu bağlantı kurulur — aksi sırada geçersiz bir kod agent
    oluşturulduktan SONRA reddedilirse "rogue" bir agent kaydı
    kalabilirdi)."""
    row = await conn.fetchrow(_CONSUME_SQL, code)
    return dict(row) if row else None


async def link_code_to_agent(conn: asyncpg.Connection, code: str, agent_id: UUID) -> None:
    """Yalnızca AUDIT amaçlı — bu kodu hangi agent'ın tükettiğini
    kaydeder. Başarısız olsa bile güvenlik garantisini etkilemez (kod
    zaten `consume_code` ile tüketilmiş durumda)."""
    await conn.execute(
        "UPDATE agent_enrollment_codes SET used_by_agent_id = $2 WHERE code = $1", code, agent_id
    )


async def list_active_codes(conn: asyncpg.Connection) -> list[dict]:
    """Süresi dolmamış VE henüz kullanılmamış kodları döner — Settings
    UI'daki "aktif kodlar" listesi için."""
    rows = await conn.fetch(
        "SELECT * FROM agent_enrollment_codes WHERE used_at IS NULL AND expires_at > now() "
        "ORDER BY created_at DESC"
    )
    return [dict(row) for row in rows]


async def delete_expired_codes(conn: asyncpg.Connection) -> int:
    """Süresi dolmuş (kullanılmış olsun olmasın) kodları siler —
    tablonun sınırsız büyümesini önlemek için. İdempotent, henüz hiçbir
    zamanlayıcı tarafından otomatik çağrılmıyor (bkz. `agent_telemetry`
    retention ile aynı desen, Faz 29 kararı)."""
    result = await conn.execute("DELETE FROM agent_enrollment_codes WHERE expires_at < now()")
    try:
        return int(result.split(" ")[1])
    except (IndexError, ValueError):
        return 0
