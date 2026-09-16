from uuid import UUID

import asyncpg

from app.db.connection import DATABASE_URL

# `users` tablosunda JSONB kolon YOK — `app/db/assets.py`/`snmp_profiles.py`
# gibi bir jsonb codec kaydına burada gerek yok.


async def get_connection() -> asyncpg.Connection:
    return await asyncpg.connect(DATABASE_URL, timeout=2)


async def count_users(conn: asyncpg.Connection) -> int:
    return await conn.fetchval("SELECT count(*) FROM users")


async def insert_user(
    conn: asyncpg.Connection,
    *,
    username: str,
    password_hash: str,
    role: str,
    full_name: str | None,
    ticket_role: str = "REQUESTER",
) -> asyncpg.Record:
    # Faz 65 — `ticket_role` (REQUESTER/TECHNICIAN/ADMIN) bilet-modülüne
    # özel rol ekseni; kolon `infra/postgres/init.sql`'de zaten var
    # (Faz 64'ten kaldı), varsayılanı REQUESTER.
    return await conn.fetchrow(
        """
        INSERT INTO users (username, password_hash, role, full_name, ticket_role)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *;
        """,
        username,
        password_hash,
        role,
        full_name,
        ticket_role,
    )


async def insert_ad_user(
    conn: asyncpg.Connection,
    *,
    username: str,
    ad_username: str,
    role: str,
    full_name: str | None,
    email: str | None,
) -> asyncpg.Record:
    """Faz 52 — LDAP bind-auth ile giriş yapan, henüz yerel bir hesabı
    OLMAYAN bir AD kullanıcısının otomatik provizyonu. `password_hash`
    KASITLI olarak `NULL` — bu satırla ASLA yerel bcrypt girişi
    yapılamaz, yalnızca LDAP bind (`app/services/ldap_auth.py`) ile
    giriş geçerlidir (bkz. `app/auth/service.py::login`'in `password_
    hash IS NULL` kontrolü)."""
    return await conn.fetchrow(
        """
        INSERT INTO users (username, password_hash, role, full_name, ad_username, is_ad_user, email)
        VALUES ($1, NULL, $2, $3, $4, true, $5)
        RETURNING *;
        """,
        username,
        role,
        full_name,
        ad_username,
        email,
    )


async def update_ad_profile(conn: asyncpg.Connection, user_id: UUID, *, full_name: str | None, email: str | None) -> None:
    """Her başarılı LDAP girişinde `displayName`/`mail`'i TAZE tutar —
    yalnızca bu iki alanı günceller, rolü/izinleri/aktiflik durumunu
    ASLA değiştirmez (bunlar admin'in elle verdiği kararlar)."""
    await conn.execute(
        "UPDATE users SET full_name = $2, email = $3, updated_at = clock_timestamp() WHERE id = $1",
        user_id,
        full_name,
        email,
    )


async def get_user_by_username(conn: asyncpg.Connection, username: str) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM users WHERE username = $1", username)


async def get_user_by_ad_username(conn: asyncpg.Connection, ad_username: str) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM users WHERE ad_username = $1", ad_username)


async def get_user_by_id(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)


async def list_users(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch("SELECT * FROM users ORDER BY created_at ASC")


async def update_user(
    conn: asyncpg.Connection,
    user_id: UUID,
    *,
    role: str | None,
    full_name: str | None,
    is_active: bool | None,
    password_hash: str | None,
    ad_username: str | None,
    ticket_role: str | None = None,
    _unset: set[str],
) -> asyncpg.Record | None:
    """`_unset` gönderilmeyen alanları taşır (Pydantic `exclude_unset`
    karşılığı) — `None` "temizle" ile "gönderilmedi"yi ayırt etmek için.
    Gerçekten hiçbir alan gönderilmemişse mevcut satırı olduğu gibi
    döner (no-op UPDATE'ten kaçınmak yerine sadeliği tercih).

    `ad_username` — Faz 49: bu yerel kullanıcıyı bir AD hesabına ELLE
    bağlar/çözer (`None` gönderilip alan set edilmişse bağlantı
    kaldırılır). `users.ad_username`'ın `ad_users(username)`'a
    `REFERENCES` kısıtı var — var olmayan bir AD kullanıcı adına
    bağlanmaya çalışmak `asyncpg.ForeignKeyViolationError` fırlatır,
    çağıran katman (bkz. app/auth/service.py) bunu 422'ye çevirir."""
    row = await conn.fetchrow(
        """
        UPDATE users SET
            role = CASE WHEN $2 THEN $3 ELSE role END,
            full_name = CASE WHEN $4 THEN $5 ELSE full_name END,
            is_active = CASE WHEN $6 THEN $7 ELSE is_active END,
            password_hash = CASE WHEN $8 THEN $9 ELSE password_hash END,
            ad_username = CASE WHEN $10 THEN $11 ELSE ad_username END,
            ticket_role = CASE WHEN $12 THEN $13 ELSE ticket_role END,
            updated_at = clock_timestamp()
        WHERE id = $1
        RETURNING *;
        """,
        user_id,
        "role" in _unset,
        role,
        "full_name" in _unset,
        full_name,
        "is_active" in _unset,
        is_active,
        "password" in _unset,
        password_hash,
        "ad_username" in _unset,
        ad_username,
        "ticket_role" in _unset,
        ticket_role,
    )
    return row


# ---- Faz 47 — ince taneli izinler --------------------------------------


async def get_permissions(conn: asyncpg.Connection, user_id: UUID) -> list[str]:
    rows = await conn.fetch("SELECT permission FROM user_permissions WHERE user_id = $1", user_id)
    return [row["permission"] for row in rows]


async def grant_permission(conn: asyncpg.Connection, user_id: UUID, permission: str) -> bool:
    """Faz 62 — TEK bir izni ekler (diğerlerine dokunmadan). Zaten
    varsa no-op. Yeni bir izin türü eklendiğinde mevcut kullanıcılara
    bir kerelik dağıtmak için (`set_permissions` tam-yer-değiştirme
    olduğu için uygun değil). Eklendiyse `True` döner."""
    result = await conn.execute(
        "INSERT INTO user_permissions (user_id, permission) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        user_id,
        permission,
    )
    return result.endswith("1")


async def set_permissions(conn: asyncpg.Connection, user_id: UUID, permissions: list[str]) -> None:
    """Kullanıcının TÜM izin setini `permissions` ile DEĞİŞTİRİR (ekleme
    değil, tam yer değiştirme) — tek bir transaction içinde sil+ekle,
    admin panelindeki checkbox matrisinin "gönderilen hal = doğru hal"
    beklentisiyle birebir eşleşir."""
    async with conn.transaction():
        await conn.execute("DELETE FROM user_permissions WHERE user_id = $1", user_id)
        if permissions:
            await conn.executemany(
                "INSERT INTO user_permissions (user_id, permission) VALUES ($1, $2)",
                [(user_id, permission) for permission in permissions],
            )
