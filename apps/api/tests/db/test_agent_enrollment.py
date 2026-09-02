"""`app/db/agent_enrollment.py` repository katmanı için gerçek
PostgreSQL'e bağlı testler (Faz 31). `db_conn` (bkz. `tests/db/
conftest.py`) transaction+rollback ile izole ediyor — gerçek veriye
etki yok."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.db.agent_enrollment import (
    consume_code,
    delete_expired_codes,
    get_code,
    insert_code,
    link_code_to_agent,
    list_active_codes,
)
from app.db.agents import insert_agent


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _seed_code(conn, code="ABC-DEF-123", ttl_minutes=10):
    return await insert_code(conn, code=code, expires_at=_now() + timedelta(minutes=ttl_minutes))


async def _seed_agent(conn):
    return await insert_agent(
        conn, hostname="h", os="linux", os_version=None, architecture=None,
        agent_version="1.0.0", local_ip=None, mac_address=None, capabilities=[],
        token_hash="fake-hash",
    )


@pytest.mark.anyio
async def test_insert_and_get_code(db_conn):
    await _seed_code(db_conn)
    row = await get_code(db_conn, "ABC-DEF-123")
    assert row is not None
    assert row["used_at"] is None


@pytest.mark.anyio
async def test_get_code_returns_none_for_unknown_code(db_conn):
    assert await get_code(db_conn, "NOPE-NOPE-NOPE") is None


@pytest.mark.anyio
async def test_consume_code_marks_used_at(db_conn):
    await _seed_code(db_conn)
    consumed = await consume_code(db_conn, "ABC-DEF-123")
    assert consumed is not None
    assert consumed["used_at"] is not None


@pytest.mark.anyio
async def test_consume_code_is_single_use(db_conn):
    await _seed_code(db_conn)
    first = await consume_code(db_conn, "ABC-DEF-123")
    second = await consume_code(db_conn, "ABC-DEF-123")

    assert first is not None
    assert second is None  # ikinci tüketim reddedilir


@pytest.mark.anyio
async def test_consume_code_returns_none_for_unknown_code(db_conn):
    assert await consume_code(db_conn, "NOPE-NOPE-NOPE") is None


@pytest.mark.anyio
async def test_link_code_to_agent_sets_used_by_agent_id(db_conn):
    await _seed_code(db_conn)
    await consume_code(db_conn, "ABC-DEF-123")
    agent = await _seed_agent(db_conn)

    await link_code_to_agent(db_conn, "ABC-DEF-123", agent["id"])

    row = await get_code(db_conn, "ABC-DEF-123")
    assert row["used_by_agent_id"] == agent["id"]


@pytest.mark.anyio
async def test_list_active_codes_excludes_used_and_expired(db_conn):
    await _seed_code(db_conn, code="ACTIVE-1-CODE", ttl_minutes=10)
    await _seed_code(db_conn, code="USED-1-CODE", ttl_minutes=10)
    await consume_code(db_conn, "USED-1-CODE")
    await _seed_code(db_conn, code="EXPIRED-1-CODE", ttl_minutes=-5)  # geçmişte sona ermiş

    active = await list_active_codes(db_conn)
    codes = {row["code"] for row in active}

    assert codes == {"ACTIVE-1-CODE"}


@pytest.mark.anyio
async def test_delete_expired_codes_removes_only_expired(db_conn):
    await _seed_code(db_conn, code="STILL-ACTIVE-1", ttl_minutes=10)
    await _seed_code(db_conn, code="LONG-EXPIRED-1", ttl_minutes=-30)

    deleted = await delete_expired_codes(db_conn)

    assert deleted == 1
    assert await get_code(db_conn, "STILL-ACTIVE-1") is not None
    assert await get_code(db_conn, "LONG-EXPIRED-1") is None


@pytest.mark.anyio
async def test_deleting_agent_sets_used_by_agent_id_null_not_cascade(db_conn):
    """`used_by_agent_id` FK'si `ON DELETE SET NULL` — agent silinirse
    enrollment kaydı SİLİNMEZ, yalnızca bağlantısı temizlenir (audit
    açısından "bu kod bir zamanlar kullanıldı" bilgisi korunur)."""
    await _seed_code(db_conn)
    await consume_code(db_conn, "ABC-DEF-123")
    agent = await _seed_agent(db_conn)
    await link_code_to_agent(db_conn, "ABC-DEF-123", agent["id"])

    await db_conn.execute("DELETE FROM agents WHERE id = $1", agent["id"])

    row = await get_code(db_conn, "ABC-DEF-123")
    assert row is not None
    assert row["used_by_agent_id"] is None
    assert row["used_at"] is not None
