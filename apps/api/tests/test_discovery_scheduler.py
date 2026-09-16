"""Faz 71 — `app/discovery/scheduler.py`. Gerçek PostgreSQL'e bağlı
(`isolated_db`), `scan_network` sahtelenir — gerçek ağ taraması
YAPILMAZ (bkz. CLAUDE.md "Discovery Engine yalnızca kullanıcının açıkça
girdiği CIDR'ı tarar" — burada zaten kayıtlı bir CIDR'ın tekrarı
test ediliyor, gerçek ICMP hiç gönderilmiyor)."""

from unittest.mock import patch

import pytest

from app.db.scheduled_scans import get_schedule, insert_schedule
from app.discovery.schemas import PingResult, ScanResult

pytestmark = pytest.mark.anyio


def _fake_result(cidr: str) -> ScanResult:
    return ScanResult(
        cidr=cidr,
        total_hosts=1,
        alive_hosts=1,
        hosts=[PingResult(ip="10.50.0.1", status="up", hostname="fake-host")],
    )


async def test_due_schedule_is_scanned_and_last_run_updated(isolated_db):
    from app.discovery import scheduler

    row = await insert_schedule(isolated_db, cidr="10.50.0.0/30", interval_hours=1, enabled=True)
    assert row["last_run_at"] is None

    with patch("app.discovery.scheduler.scan_network", return_value=_fake_result("10.50.0.0/30")):
        await scheduler._run_once()

    updated = await get_schedule(isolated_db, row["id"])
    assert updated["last_run_at"] is not None
    assert updated["last_run_status"] == "success"
    assert updated["last_run_error"] is None


async def test_disabled_schedule_is_skipped(isolated_db):
    from app.discovery import scheduler

    row = await insert_schedule(isolated_db, cidr="10.50.1.0/30", interval_hours=1, enabled=False)

    with patch("app.discovery.scheduler.scan_network") as mock_scan:
        await scheduler._run_once()
        mock_scan.assert_not_called()

    updated = await get_schedule(isolated_db, row["id"])
    assert updated["last_run_at"] is None


async def test_not_yet_due_schedule_is_skipped(isolated_db):
    from app.discovery import scheduler

    row = await insert_schedule(isolated_db, cidr="10.50.2.0/30", interval_hours=24, enabled=True)
    with patch("app.discovery.scheduler.scan_network", return_value=_fake_result("10.50.2.0/30")):
        await scheduler._run_once()
    first_run = (await get_schedule(isolated_db, row["id"]))["last_run_at"]
    assert first_run is not None

    # Hemen ikinci turda (interval_hours=24) henüz süresi gelmedi.
    with patch("app.discovery.scheduler.scan_network") as mock_scan:
        await scheduler._run_once()
        mock_scan.assert_not_called()
    assert (await get_schedule(isolated_db, row["id"]))["last_run_at"] == first_run


async def test_one_schedule_failure_does_not_block_another(isolated_db):
    from app.discovery import scheduler

    failing = await insert_schedule(isolated_db, cidr="10.50.3.0/30", interval_hours=1, enabled=True)
    healthy = await insert_schedule(isolated_db, cidr="10.50.4.0/30", interval_hours=1, enabled=True)

    def _side_effect(cidr: str):
        if cidr == "10.50.3.0/30":
            raise RuntimeError("simulated scan failure")
        return _fake_result(cidr)

    with patch("app.discovery.scheduler.scan_network", side_effect=_side_effect):
        await scheduler._run_once()

    failing_row = await get_schedule(isolated_db, failing["id"])
    healthy_row = await get_schedule(isolated_db, healthy["id"])
    assert failing_row["last_run_status"] == "error"
    assert "simulated scan failure" in failing_row["last_run_error"]
    assert healthy_row["last_run_status"] == "success"


def test_scheduler_enabled_by_default(monkeypatch):
    from app.discovery.scheduler import is_discovery_scheduler_enabled

    monkeypatch.delenv("DISCOVERY_SCHEDULER_ENABLED", raising=False)
    assert is_discovery_scheduler_enabled() is True
    monkeypatch.setenv("DISCOVERY_SCHEDULER_ENABLED", "false")
    assert is_discovery_scheduler_enabled() is False
