from uuid import UUID

import asyncpg

from app.db.connection import DATABASE_URL

# `ldap_config`/`ad_groups`/`ad_users`/`ad_group_memberships`'te JSONB
# kolon YOK — bir jsonb codec kaydına gerek yok.


async def get_connection() -> asyncpg.Connection:
    return await asyncpg.connect(DATABASE_URL, timeout=2)


# ---- ldap_config ------------------------------------------------------


async def get_config(conn: asyncpg.Connection) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM ldap_config WHERE id = 1")


async def upsert_config(
    conn: asyncpg.Connection,
    *,
    host: str,
    port: int,
    use_ssl: bool,
    domain_fqdn: str,
    base_dn: str,
    bind_dn: str,
    encrypted_bind_password: str,
) -> asyncpg.Record:
    return await conn.fetchrow(
        """
        INSERT INTO ldap_config (id, host, port, use_ssl, domain_fqdn, base_dn, bind_dn, encrypted_bind_password)
        VALUES (1, $1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (id) DO UPDATE SET
            host = EXCLUDED.host,
            port = EXCLUDED.port,
            use_ssl = EXCLUDED.use_ssl,
            domain_fqdn = EXCLUDED.domain_fqdn,
            base_dn = EXCLUDED.base_dn,
            bind_dn = EXCLUDED.bind_dn,
            encrypted_bind_password = EXCLUDED.encrypted_bind_password,
            updated_at = clock_timestamp()
        RETURNING *;
        """,
        host,
        port,
        use_ssl,
        domain_fqdn,
        base_dn,
        bind_dn,
        encrypted_bind_password,
    )


async def record_sync_result(conn: asyncpg.Connection, *, status: str, error: str | None) -> None:
    """`error` gerçek bir üçüncü parti (ldap3) exception'ın `str()`'i
    olabilir — GERÇEK bir canlı denemede bunun bir NUL (`0x00`) baytı
    İÇERDİĞİ gözlemlendi (ör. bozuk bir TLS/socket yanıtından sızan ham
    bayt). PostgreSQL'in `text` kolonları NUL baytını KABUL ETMEZ
    (`CharacterNotInRepertoireError`) — bu, bir sync HATASINI
    kaydetmeye çalışırken kendisi 500 ile çökme riski taşıdığı için
    burada temizleniyor (kullanıcıya dürüst hata mesajı gösterme
    yolunun kendisi bir hataya takılmamalı)."""
    if error is not None:
        error = error.replace("\x00", "")
    await conn.execute(
        "UPDATE ldap_config SET last_sync_status = $1, last_sync_error = $2, last_sync_at = clock_timestamp() WHERE id = 1",
        status,
        error,
    )


# ---- AD dizin yansıması (ad_groups/ad_users/ad_group_memberships) -----


async def replace_groups(conn: asyncpg.Connection, groups: list[dict]) -> dict[str, UUID]:
    """`groups`'u (`[{"dn":..., "name":...}]`) tam olarak yansıtır —
    AD'de artık bulunmayan gruplar SİLİNİR (CASCADE ile `pam_access_
    rules`'daki o gruba bağlı kuralları da temizler — bilinçli: AD'den
    silinen bir grubun erişim yetkisi de sessizce ASILI KALMAMALI).
    Dönüş: `{distinguished_name: id}` (üyelik senkronizasyonunda
    kullanılmak üzere)."""
    dns = [g["dn"] for g in groups]
    await conn.execute("DELETE FROM ad_groups WHERE NOT (distinguished_name = ANY($1::text[]))", dns)
    rows = await conn.fetch(
        """
        INSERT INTO ad_groups (distinguished_name, name, synced_at)
        SELECT dn, name, clock_timestamp() FROM unnest($1::text[], $2::text[]) AS t(dn, name)
        ON CONFLICT (distinguished_name) DO UPDATE SET name = EXCLUDED.name, synced_at = clock_timestamp()
        RETURNING id, distinguished_name;
        """,
        dns,
        [g["name"] for g in groups],
    )
    return {row["distinguished_name"]: row["id"] for row in rows}


async def replace_users(conn: asyncpg.Connection, users: list[dict]) -> dict[str, UUID]:
    """`replace_groups` ile AYNI desen. `users.ad_username` bir silinen
    AD kullanıcısına ATIFTA bulunuyorsa (`ad_users.username` FK'sı,
    `ON DELETE SET NULL`) o bağlantı otomatik temizlenir — yerel hesap
    SİLİNMEZ, yalnızca AD bağlantısı kopar."""
    dns = [u["dn"] for u in users]
    await conn.execute("DELETE FROM ad_users WHERE NOT (distinguished_name = ANY($1::text[]))", dns)
    rows = await conn.fetch(
        """
        INSERT INTO ad_users (distinguished_name, username, display_name, email, synced_at)
        SELECT dn, username, display_name, email, clock_timestamp()
        FROM unnest($1::text[], $2::text[], $3::text[], $4::text[]) AS t(dn, username, display_name, email)
        ON CONFLICT (distinguished_name) DO UPDATE SET
            username = EXCLUDED.username,
            display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            synced_at = clock_timestamp()
        RETURNING id, distinguished_name;
        """,
        dns,
        [u["username"] for u in users],
        [u["display_name"] for u in users],
        [u.get("email") for u in users],
    )
    return {row["distinguished_name"]: row["id"] for row in rows}


async def replace_memberships(conn: asyncpg.Connection, memberships: list[tuple[UUID, UUID]]) -> None:
    await conn.execute("TRUNCATE TABLE ad_group_memberships")
    if memberships:
        await conn.executemany(
            "INSERT INTO ad_group_memberships (ad_user_id, ad_group_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            memberships,
        )


async def list_groups(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch("SELECT * FROM ad_groups ORDER BY name ASC")


async def list_users(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    """Faz 52 — `/pam/users`'ın "Active Directory'den İçe Aktar" seçici
    listesinin veri kaynağı."""
    return await conn.fetch("SELECT * FROM ad_users ORDER BY username ASC")


async def get_ad_user_by_username(conn: asyncpg.Connection, username: str) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM ad_users WHERE username = $1", username)


async def get_group_ids_for_username(conn: asyncpg.Connection, ad_username: str) -> list[UUID]:
    """Bir AD kullanıcı adının (`sAMAccountName`) DOĞRUDAN üyesi olduğu
    grupların id listesi — `app/pam/service.py`'deki grup-bazlı
    yetkilendirme kontrolünün veri kaynağı."""
    rows = await conn.fetch(
        """
        SELECT m.ad_group_id
        FROM ad_group_memberships m
        JOIN ad_users u ON u.id = m.ad_user_id
        WHERE u.username = $1;
        """,
        ad_username,
    )
    return [row["ad_group_id"] for row in rows]
