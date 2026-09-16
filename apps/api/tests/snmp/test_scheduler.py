"""`app/snmp/scheduler.py` için birim testleri — gerçek bir SNMP ağ
isteği/DB bağlantısı hiç kullanılmaz. `run_background_poller`'ın
sonsuz döngüsü ASLA doğrudan çalıştırılmaz (test asla bitmez) — yalnızca
`_run_once` (tek tur) ve env-parsing yardımcıları test edilir."""

from unittest.mock import AsyncMock, patch

import pytest

from app.snmp import monitoring_cache, scheduler

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def _reset_cache():
    monitoring_cache.reset()
    yield
    monitoring_cache.reset()


class _FakeConn:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


def test_background_polling_enabled_by_default(monkeypatch):
    monkeypatch.delenv("SNMP_BACKGROUND_POLLING_ENABLED", raising=False)
    assert scheduler.is_background_polling_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "False", "NO"])
def test_background_polling_can_be_disabled(monkeypatch, value):
    monkeypatch.setenv("SNMP_BACKGROUND_POLLING_ENABLED", value)
    assert scheduler.is_background_polling_enabled() is False


def test_interval_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("SNMP_POLL_INTERVAL_SECONDS", raising=False)
    assert scheduler._interval_seconds() == 30


def test_interval_uses_env_value(monkeypatch):
    monkeypatch.setenv("SNMP_POLL_INTERVAL_SECONDS", "10")
    assert scheduler._interval_seconds() == 10


@pytest.mark.parametrize("value", ["not-a-number", "-5", "0"])
def test_interval_falls_back_to_default_when_invalid(monkeypatch, value):
    monkeypatch.setenv("SNMP_POLL_INTERVAL_SECONDS", value)
    assert scheduler._interval_seconds() == 30


async def test_run_once_records_a_batch_when_db_reachable():
    conn = _FakeConn()
    fake_batch = object()

    with (
        patch("app.snmp.scheduler.get_connection", AsyncMock(return_value=conn)),
        patch("app.snmp.scheduler.list_assets", AsyncMock(return_value=[{"id": "a"}])),
        patch(
            "app.snmp.scheduler.PollingEngine.poll_all",
            AsyncMock(return_value=fake_batch),
        ),
        patch("app.snmp.scheduler.record_batch") as record_mock,
    ):
        await scheduler._run_once()

    record_mock.assert_called_once_with(fake_batch)
    assert conn.closed is True


async def test_run_once_never_raises_when_database_unreachable():
    with patch("app.snmp.scheduler.get_connection", AsyncMock(side_effect=OSError("refused"))):
        await scheduler._run_once()  # exception fırlatmamalı


async def test_run_once_never_raises_on_unexpected_error_and_still_closes_connection():
    conn = _FakeConn()
    with (
        patch("app.snmp.scheduler.get_connection", AsyncMock(return_value=conn)),
        patch("app.snmp.scheduler.list_assets", AsyncMock(side_effect=RuntimeError("boom"))),
    ):
        await scheduler._run_once()  # exception fırlatmamalı, worker'ı durdurmamalı

    assert conn.closed is True
