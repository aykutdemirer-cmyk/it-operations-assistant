from unittest.mock import MagicMock, patch

import psutil
import pytest

from agent.collectors import processes


def _fake_process(pid, name, cpu, mem, username="user1", status="running"):
    proc = MagicMock()
    proc.info = {"pid": pid, "name": name, "cpu_percent": cpu, "memory_percent": mem, "username": username, "status": status}
    return proc


def test_collect_processes_returns_normalized_fields():
    procs = [_fake_process(1, "postgres.exe", 5.0, 3.0)]
    with (
        patch("agent.collectors.processes.psutil.process_iter", return_value=procs),
        patch("agent.collectors.processes.psutil.cpu_count", return_value=1),
    ):
        result = processes.collect_processes()

    assert result == [
        {"pid": 1, "name": "postgres.exe", "cpu_percent": 5.0, "memory_percent": 3.0, "username": "user1", "status": "running"}
    ]


def test_collect_processes_normalizes_cpu_percent_by_core_count():
    """Gerçek kullanıcı bildirimi: `System Idle Process` gibi süreçler
    çok çekirdekli bir makinede %1124 gibi değerler gösteriyordu —
    `psutil.Process.cpu_percent()` çekirdek sayısına göre NORMALİZE
    EDİLMEMİŞ döner. Artık Görev Yöneticisi'yle tutarlı 0-100% ölçeğine
    normalize ediliyor."""
    procs = [_fake_process(0, "System Idle Process", 1124.0, 0.0)]
    with (
        patch("agent.collectors.processes.psutil.process_iter", return_value=procs),
        patch("agent.collectors.processes.psutil.cpu_count", return_value=12),
    ):
        result = processes.collect_processes()

    assert result[0]["cpu_percent"] == pytest.approx(1124.0 / 12)
    assert result[0]["cpu_percent"] <= 100.0


def test_collect_processes_clamps_cpu_percent_to_100_even_if_measurement_noise_exceeds_it():
    procs = [_fake_process(1, "burst.exe", 150.0, 0.0)]
    with (
        patch("agent.collectors.processes.psutil.process_iter", return_value=procs),
        patch("agent.collectors.processes.psutil.cpu_count", return_value=1),
    ):
        result = processes.collect_processes()

    assert result[0]["cpu_percent"] == 100.0


def test_collect_processes_handles_none_cpu_percent_honestly():
    procs = [_fake_process(1, "unknown.exe", None, 0.0)]
    with (
        patch("agent.collectors.processes.psutil.process_iter", return_value=procs),
        patch("agent.collectors.processes.psutil.cpu_count", return_value=8),
    ):
        result = processes.collect_processes()

    assert result[0]["cpu_percent"] is None


def test_collect_processes_falls_back_to_single_core_when_cpu_count_unavailable():
    procs = [_fake_process(1, "app.exe", 42.0, 0.0)]
    with (
        patch("agent.collectors.processes.psutil.process_iter", return_value=procs),
        patch("agent.collectors.processes.psutil.cpu_count", side_effect=RuntimeError("boom")),
    ):
        result = processes.collect_processes()

    assert result[0]["cpu_percent"] == 42.0


def test_collect_processes_never_includes_cmdline_field():
    procs = [_fake_process(1, "app.exe", 1.0, 1.0)]
    with patch("agent.collectors.processes.psutil.process_iter", return_value=procs):
        result = processes.collect_processes()

    assert "cmdline" not in result[0]


def test_collect_processes_sorted_by_cpu_then_memory_descending():
    procs = [
        _fake_process(1, "low", 1.0, 1.0),
        _fake_process(2, "high", 90.0, 10.0),
        _fake_process(3, "mid", 50.0, 5.0),
    ]
    with patch("agent.collectors.processes.psutil.process_iter", return_value=procs):
        result = processes.collect_processes()

    assert [p["pid"] for p in result] == [2, 3, 1]


def test_collect_processes_respects_limit():
    procs = [_fake_process(i, f"proc{i}", float(i), 0.0) for i in range(10)]
    with patch("agent.collectors.processes.psutil.process_iter", return_value=procs):
        result = processes.collect_processes(limit=3)

    assert len(result) == 3


def test_collect_processes_skips_processes_that_vanish_mid_iteration():
    good = _fake_process(1, "alive", 1.0, 1.0)
    gone = MagicMock()
    type(gone).info = property(lambda self: (_ for _ in ()).throw(psutil.NoSuchProcess(999)))

    with patch("agent.collectors.processes.psutil.process_iter", return_value=[good, gone]):
        result = processes.collect_processes()

    assert len(result) == 1
    assert result[0]["pid"] == 1


def test_collect_processes_returns_empty_list_when_iteration_unavailable():
    with patch("agent.collectors.processes.psutil.process_iter", side_effect=RuntimeError("boom")):
        assert processes.collect_processes() == []
