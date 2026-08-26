import pytest

from app.db.assets import ensure_schema, get_connection


@pytest.fixture
async def db_conn():
    """Gerçek PostgreSQL'e bağlanır, `assets` şemasını garanti eder ve
    testi bir transaction içinde çalıştırıp sonunda rollback yapar (test
    verisi kalıcı DB'yi kirletmez). PostgreSQL erişilemezse test'i açık
    bir nedenle skip eder — mock database kullanılmaz."""
    try:
        conn = await get_connection()
    except OSError:
        pytest.skip(
            "PostgreSQL erişilemiyor — önce "
            "`docker compose -f infra/docker-compose.yml up -d` çalıştırın"
        )
        return

    await ensure_schema(conn)
    transaction = conn.transaction()
    await transaction.start()
    try:
        yield conn
    finally:
        await transaction.rollback()
        await conn.close()
