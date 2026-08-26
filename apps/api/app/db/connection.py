import os

import asyncpg

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://itops:itops@localhost:5432/itops"
)


async def check_db_connection() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.fetchval("SELECT 1")
    finally:
        await conn.close()
