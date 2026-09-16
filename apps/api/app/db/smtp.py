"""Faz 66 — `smtp_config` (tek satırlık SMTP yapılandırması) DB katmanı.
`app/db/ldap.py::ldap_config` ile AYNI desen."""

import asyncpg

from app.db.connection import DATABASE_URL


async def get_connection() -> asyncpg.Connection:
    return await asyncpg.connect(DATABASE_URL, timeout=2)


async def get_config(conn: asyncpg.Connection) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM smtp_config WHERE id = 1")


async def upsert_config(
    conn: asyncpg.Connection,
    *,
    enabled: bool,
    server: str,
    port: int,
    encryption: str,
    username: str,
    encrypted_password: str,
    from_email: str,
    from_name: str,
    it_group_email: str,
    base_url: str,
) -> asyncpg.Record:
    return await conn.fetchrow(
        """
        INSERT INTO smtp_config
            (id, enabled, server, port, encryption, username, encrypted_password, from_email, from_name, it_group_email, base_url)
        VALUES (1, $1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (id) DO UPDATE SET
            enabled = EXCLUDED.enabled,
            server = EXCLUDED.server,
            port = EXCLUDED.port,
            encryption = EXCLUDED.encryption,
            username = EXCLUDED.username,
            encrypted_password = EXCLUDED.encrypted_password,
            from_email = EXCLUDED.from_email,
            from_name = EXCLUDED.from_name,
            it_group_email = EXCLUDED.it_group_email,
            base_url = EXCLUDED.base_url,
            updated_at = clock_timestamp()
        RETURNING *;
        """,
        enabled,
        server,
        port,
        encryption,
        username,
        encrypted_password,
        from_email,
        from_name,
        it_group_email,
        base_url,
    )


async def record_test_result(conn: asyncpg.Connection, *, status: str, error: str | None) -> None:
    if error is not None:
        error = error.replace("\x00", "")
    await conn.execute(
        "UPDATE smtp_config SET last_test_status = $1, last_test_error = $2, last_test_at = clock_timestamp() WHERE id = 1",
        status,
        error,
    )
