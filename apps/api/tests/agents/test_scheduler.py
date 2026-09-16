"""`app/agents/scheduler.py` için birim testleri — gerçek bir DB
bağlantısı hiç kullanılmaz. `run_agent_maintenance`'ın sonsuz döngüsü
ASLA doğrudan çalıştırılmaz (test asla bitmez) — yalnızca `_run_once`/
`_archive_inactive_agents` (tek tur) ve env-parsing yardımcıları test
edilir (bkz. `tests/snmp/test_scheduler.py` — AYNI desen)."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agents import scheduler

pytestmark = pytest.mark.anyio


class _FakeConn:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


def test_maintenance_enabled_by_default(monkeypatch):
    monkeypatch.delenv("AGENT_MAINTENANCE_ENABLED", raising=False)
    assert scheduler.is_agent_maintenance_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "False", "NO"])
def test_maintenance_can_be_disabled(monkeypatch, value):
    monkeypatch.setenv("AGENT_MAINTENANCE_ENABLED", value)
    assert scheduler.is_agent_maintenance_enabled() is False


def test_interval_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("AGENT_MAINTENANCE_INTERVAL_SECONDS", raising=False)
    assert scheduler._interval_seconds() == 3600


def test_interval_uses_env_value(monkeypatch):
    monkeypatch.setenv("AGENT_MAINTENANCE_INTERVAL_SECONDS", "60")
    assert scheduler._interval_seconds() == 60


@pytest.mark.parametrize("value", ["not-a-number", "-5", "0"])
def test_interval_falls_back_to_default_when_invalid(monkeypatch, value):
    monkeypatch.setenv("AGENT_MAINTENANCE_INTERVAL_SECONDS", value)
    assert scheduler._interval_seconds() == 3600


async def test_archive_inactive_agents_skips_when_policy_disabled():
    conn = _FakeConn()
    with (
        patch("app.agents.scheduler.get_retention_policy", AsyncMock(return_value={"enabled": False, "retention_days": 30})),
        patch("app.agents.scheduler.list_inactive_agent_ids", AsyncMock()) as list_mock,
    ):
        count = await scheduler._archive_inactive_agents(conn)

    assert count == 0
    list_mock.assert_not_called()


async def test_archive_inactive_agents_archives_each_inactive_id_when_enabled():
    conn = _FakeConn()
    ids = [uuid4(), uuid4()]
    with (
        patch(
            "app.agents.scheduler.get_retention_policy",
            AsyncMock(return_value={"enabled": True, "retention_days": 14}),
        ),
        patch("app.agents.scheduler.list_inactive_agent_ids", AsyncMock(return_value=ids)),
        patch("app.agents.scheduler.archive_agent", AsyncMock()) as archive_mock,
    ):
        count = await scheduler._archive_inactive_agents(conn)

    assert count == 2
    assert archive_mock.await_count == 2
    archive_mock.assert_any_await(conn, ids[0], reason="inactivity", inactive_days=14)
    archive_mock.assert_any_await(conn, ids[1], reason="inactivity", inactive_days=14)


async def test_run_once_never_raises_when_database_unreachable():
    with patch("app.agents.scheduler.get_connection", AsyncMock(side_effect=OSError("refused"))):
        await scheduler._run_once()  # exception fırlatmamalı


async def test_run_once_closes_connection_and_calls_both_maintenance_steps():
    conn = _FakeConn()
    with (
        patch("app.agents.scheduler.get_connection", AsyncMock(return_value=conn)),
        patch("app.agents.scheduler._archive_inactive_agents", AsyncMock(return_value=0)) as archive_mock,
        patch("app.agents.scheduler.cleanup_expired_telemetry", AsyncMock(return_value=0)) as cleanup_mock,
    ):
        await scheduler._run_once()

    archive_mock.assert_awaited_once_with(conn)
    cleanup_mock.assert_awaited_once_with(conn)
    assert conn.closed is True


async def test_run_once_never_raises_when_archiving_fails_and_still_runs_cleanup():
    conn = _FakeConn()
    with (
        patch("app.agents.scheduler.get_connection", AsyncMock(return_value=conn)),
        patch("app.agents.scheduler._archive_inactive_agents", AsyncMock(side_effect=RuntimeError("boom"))),
        patch("app.agents.scheduler.cleanup_expired_telemetry", AsyncMock(return_value=0)) as cleanup_mock,
    ):
        await scheduler._run_once()  # exception fırlatmamalı, worker'ı durdurmamalı

    cleanup_mock.assert_awaited_once_with(conn)
    assert conn.closed is True


async def test_run_once_never_raises_when_cleanup_fails():
    conn = _FakeConn()
    with (
        patch("app.agents.scheduler.get_connection", AsyncMock(return_value=conn)),
        patch("app.agents.scheduler._archive_inactive_agents", AsyncMock(return_value=0)),
        patch("app.agents.scheduler.cleanup_expired_telemetry", AsyncMock(side_effect=RuntimeError("boom"))),
    ):
        await scheduler._run_once()  # exception fırlatmamalı

    assert conn.closed is True
