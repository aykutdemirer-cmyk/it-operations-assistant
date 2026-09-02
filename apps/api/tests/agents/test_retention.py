"""`agent_telemetry` retention temizliği için testler (Faz 29). Gerçek
PostgreSQL'e karşı, `isolated_db` (bkz. kök `conftest.py`) ile tam
rollback-izolasyonlu — gerçek veriye hiçbir etki yok."""

from datetime import datetime, timedelta, timezone

import pytest

from app.agents.service import cleanup_expired_telemetry, telemetry_retention_days
from app.db.agents import delete_expired_telemetry, insert_agent, insert_telemetry


async def _seed_agent(conn) -> dict:
    return await insert_agent(
        conn,
        hostname="retention-test-host",
        os="linux",
        os_version=None,
        architecture=None,
        agent_version="1.0.0",
        local_ip=None,
        mac_address=None,
        capabilities=[],
        token_hash="fake-hash-for-retention-test",
    )


async def _seed_telemetry(conn, agent_id, collected_at) -> None:
    await insert_telemetry(
        conn,
        agent_id=agent_id,
        collected_at=collected_at,
        cpu_percent=10.0,
        memory_total_bytes=None,
        memory_used_bytes=None,
        memory_percent=None,
        disks=[],
        network_interfaces=[],
    )


def test_telemetry_retention_days_reads_env(monkeypatch):
    monkeypatch.setenv("AGENT_TELEMETRY_RETENTION_DAYS", "7")
    assert telemetry_retention_days() == 7


def test_telemetry_retention_days_default_is_safe(monkeypatch):
    monkeypatch.delenv("AGENT_TELEMETRY_RETENTION_DAYS", raising=False)
    value = telemetry_retention_days()
    assert 1 <= value <= 90


def test_telemetry_retention_days_invalid_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("AGENT_TELEMETRY_RETENTION_DAYS", "not-a-number")
    default = telemetry_retention_days()
    monkeypatch.setenv("AGENT_TELEMETRY_RETENTION_DAYS", "-5")
    assert telemetry_retention_days() == default


@pytest.mark.anyio
async def test_delete_expired_telemetry_removes_only_old_rows(isolated_db):
    agent = await _seed_agent(isolated_db)
    now = datetime.now(timezone.utc)
    await _seed_telemetry(isolated_db, agent["id"], now - timedelta(days=40))
    await _seed_telemetry(isolated_db, agent["id"], now - timedelta(days=1))

    deleted = await delete_expired_telemetry(isolated_db, retention_days=30)

    assert deleted == 1
    remaining = await isolated_db.fetch("SELECT collected_at FROM agent_telemetry WHERE agent_id = $1", agent["id"])
    assert len(remaining) == 1


@pytest.mark.anyio
async def test_delete_expired_telemetry_is_idempotent(isolated_db):
    agent = await _seed_agent(isolated_db)
    await _seed_telemetry(isolated_db, agent["id"], datetime.now(timezone.utc) - timedelta(days=40))

    first = await delete_expired_telemetry(isolated_db, retention_days=30)
    second = await delete_expired_telemetry(isolated_db, retention_days=30)

    assert first == 1
    assert second == 0


@pytest.mark.anyio
async def test_delete_expired_telemetry_rejects_non_positive_retention(isolated_db):
    with pytest.raises(ValueError):
        await delete_expired_telemetry(isolated_db, retention_days=0)


@pytest.mark.anyio
async def test_cleanup_expired_telemetry_uses_configured_retention(isolated_db, monkeypatch):
    monkeypatch.setenv("AGENT_TELEMETRY_RETENTION_DAYS", "5")
    agent = await _seed_agent(isolated_db)
    await _seed_telemetry(isolated_db, agent["id"], datetime.now(timezone.utc) - timedelta(days=10))
    await _seed_telemetry(isolated_db, agent["id"], datetime.now(timezone.utc) - timedelta(days=1))

    deleted = await cleanup_expired_telemetry(isolated_db)

    assert deleted == 1


@pytest.mark.anyio
async def test_delete_expired_telemetry_never_touches_other_agents_rows(isolated_db):
    agent_a = await _seed_agent(isolated_db)
    agent_b = await insert_agent(
        isolated_db,
        hostname="retention-test-host-b",
        os="linux",
        os_version=None,
        architecture=None,
        agent_version="1.0.0",
        local_ip=None,
        mac_address=None,
        capabilities=[],
        token_hash="fake-hash-for-retention-test-b",
    )
    old = datetime.now(timezone.utc) - timedelta(days=40)
    await _seed_telemetry(isolated_db, agent_a["id"], old)
    await _seed_telemetry(isolated_db, agent_b["id"], old)

    deleted = await delete_expired_telemetry(isolated_db, retention_days=30)

    assert deleted == 2
