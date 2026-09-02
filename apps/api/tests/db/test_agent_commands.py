"""`app/db/agent_commands.py` repository katmanı için gerçek PostgreSQL'e
bağlı testler (Faz 33). `db_conn` transaction+rollback ile izole eder."""

import pytest

from app.db.agent_commands import (
    complete_command,
    create_command,
    create_rejected_command,
    get_command,
    list_commands_for_agent,
    list_pending_and_mark_sent,
)
from app.db.agents import insert_agent


async def _seed_agent(conn):
    return await insert_agent(
        conn, hostname="h", os="linux", os_version=None, architecture=None,
        agent_version="1.0.0", local_ip=None, mac_address=None, capabilities=[],
        token_hash="fake-hash",
    )


@pytest.mark.anyio
async def test_create_command_starts_pending(db_conn):
    agent = await _seed_agent(db_conn)
    row = await create_command(
        db_conn, agent_id=agent["id"], command_type="kill_process", action="kill",
        target="1234", requested_by=None,
    )
    assert row["status"] == "pending"
    assert row["target"] == "1234"


@pytest.mark.anyio
async def test_create_rejected_command_is_terminal_immediately(db_conn):
    agent = await _seed_agent(db_conn)
    row = await create_rejected_command(
        db_conn, agent_id=agent["id"], command_type="kill_process", action="kill",
        target="4", requested_by=None, reason="sistem süreci",
    )
    assert row["status"] == "rejected"
    assert row["result_detail"] == "sistem süreci"
    assert row["completed_at"] is not None


@pytest.mark.anyio
async def test_list_pending_and_mark_sent_returns_and_transitions(db_conn):
    agent = await _seed_agent(db_conn)
    await create_command(
        db_conn, agent_id=agent["id"], command_type="service_control", action="restart",
        target="spooler", requested_by=None,
    )

    pending = await list_pending_and_mark_sent(db_conn, agent["id"])
    assert len(pending) == 1
    assert pending[0]["status"] == "sent"

    # İkinci çağrıda artık bekleyen komut yok — aynı komut iki kez çekilmiyor.
    second_pull = await list_pending_and_mark_sent(db_conn, agent["id"])
    assert second_pull == []


@pytest.mark.anyio
async def test_complete_command_sets_result_and_completed_at(db_conn):
    agent = await _seed_agent(db_conn)
    created = await create_command(
        db_conn, agent_id=agent["id"], command_type="kill_process", action="kill",
        target="5555", requested_by=None,
    )

    updated = await complete_command(
        db_conn, command_id=created["id"], status="succeeded", result_detail="PID 5555 sonlandırıldı"
    )
    assert updated["status"] == "succeeded"
    assert updated["result_detail"] == "PID 5555 sonlandırıldı"
    assert updated["completed_at"] is not None


@pytest.mark.anyio
async def test_list_commands_for_agent_orders_newest_first(db_conn):
    agent = await _seed_agent(db_conn)
    first = await create_command(
        db_conn, agent_id=agent["id"], command_type="kill_process", action="kill",
        target="1", requested_by=None,
    )
    second = await create_command(
        db_conn, agent_id=agent["id"], command_type="kill_process", action="kill",
        target="2", requested_by=None,
    )

    rows = await list_commands_for_agent(db_conn, agent["id"])
    assert [r["id"] for r in rows][:2] == [second["id"], first["id"]]


@pytest.mark.anyio
async def test_get_command_returns_none_for_unknown_id(db_conn):
    import uuid

    assert await get_command(db_conn, uuid.uuid4()) is None
