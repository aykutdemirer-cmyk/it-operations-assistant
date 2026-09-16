import asyncpg

from app.db.connection import DATABASE_URL

# `vcenter_config`'te JSONB kolon YOK — bir jsonb codec kaydına gerek yok.


async def get_connection() -> asyncpg.Connection:
    return await asyncpg.connect(DATABASE_URL, timeout=2)


async def get_config(conn: asyncpg.Connection) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM vcenter_config WHERE id = 1")


async def upsert_config(
    conn: asyncpg.Connection,
    *,
    host: str,
    port: int,
    username: str,
    encrypted_password: str,
    verify_ssl: bool,
) -> asyncpg.Record:
    return await conn.fetchrow(
        """
        INSERT INTO vcenter_config (id, host, port, username, encrypted_password, verify_ssl)
        VALUES (1, $1, $2, $3, $4, $5)
        ON CONFLICT (id) DO UPDATE SET
            host = EXCLUDED.host,
            port = EXCLUDED.port,
            username = EXCLUDED.username,
            encrypted_password = EXCLUDED.encrypted_password,
            verify_ssl = EXCLUDED.verify_ssl,
            updated_at = clock_timestamp()
        RETURNING *;
        """,
        host,
        port,
        username,
        encrypted_password,
        verify_ssl,
    )


async def record_test_result(conn: asyncpg.Connection, *, status: str, error: str | None) -> None:
    """`error` gerçek bir üçüncü parti (httpx) exception'ın `str()`'i
    olabilir — `ldap_config::record_sync_result` ile AYNI ihtiyatla
    olası bir NUL baytı temizlenir (PostgreSQL `text` kolonları bunu
    kabul etmez)."""
    if error is not None:
        error = error.replace("\x00", "")
    await conn.execute(
        "UPDATE vcenter_config SET last_test_status = $1, last_test_error = $2, last_test_at = clock_timestamp() WHERE id = 1",
        status,
        error,
    )
