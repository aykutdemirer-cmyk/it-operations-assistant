"""`agent/commands.py` için testler (Faz 33). Gerçek bir süreç/servis
ASLA öldürülmez/durdurulmaz — `subprocess.run` mock'lanır."""

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agent.commands import (
    CommandResult,
    control_power,
    control_service,
    execute,
    kill_process,
    logoff,
    reboot,
    shutdown,
)


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# --- kill_process: blacklist ---


@pytest.mark.parametrize("pid", [0, 1, 4])
def test_kill_process_rejects_protected_pids(pid):
    result = kill_process(pid)
    assert result.success is False
    assert "reddedildi" in result.detail


def test_kill_process_rejects_own_pid():
    result = kill_process(os.getpid())
    assert result.success is False
    assert "kendi sürecini" in result.detail


def test_kill_process_rejects_protected_process_name():
    fake_proc = MagicMock()
    fake_proc.name.return_value = "svchost.exe"
    with patch("psutil.Process", return_value=fake_proc):
        result = kill_process(9999)
    assert result.success is False
    assert "korumalı" in result.detail


# --- kill_process: gerçek çalıştırma (mock subprocess) ---


def test_kill_process_windows_uses_taskkill():
    fake_proc = MagicMock()
    fake_proc.name.return_value = "notepad.exe"
    with (
        patch("psutil.Process", return_value=fake_proc),
        patch("agent.commands.current_os", return_value="windows"),
        patch("agent.commands._run", return_value=_completed(0)) as run_mock,
    ):
        result = kill_process(9999)

    assert result.success is True
    run_mock.assert_called_once_with(["taskkill", "/F", "/PID", "9999"])


def test_kill_process_linux_uses_kill_minus_9():
    fake_proc = MagicMock()
    fake_proc.name.return_value = "python3"
    with (
        patch("psutil.Process", return_value=fake_proc),
        patch("agent.commands.current_os", return_value="linux"),
        patch("agent.commands._run", return_value=_completed(0)) as run_mock,
    ):
        result = kill_process(9999)

    assert result.success is True
    run_mock.assert_called_once_with(["kill", "-9", "9999"])


def test_kill_process_reports_failure_from_nonzero_exit():
    with (
        patch("psutil.Process", side_effect=Exception("no such process")),
        patch("agent.commands.current_os", return_value="linux"),
        patch("agent.commands._run", return_value=_completed(1, stderr="No such process")),
    ):
        result = kill_process(9999)

    assert result.success is False
    assert "No such process" in result.detail


# --- control_service: blacklist ---


def test_control_service_rejects_protected_service_name():
    result = control_service("sshd", "stop")
    assert result.success is False
    assert "korumalı" in result.detail


def test_control_service_rejects_blank_name():
    result = control_service("   ", "start")
    assert result.success is False


def test_control_service_rejects_unknown_action():
    result = control_service("MyApp", "pause")
    assert result.success is False


# --- control_service: gerçek çalıştırma ---


def test_control_service_windows_start():
    with (
        patch("agent.commands.current_os", return_value="windows"),
        patch("agent.commands._run", return_value=_completed(0)) as run_mock,
    ):
        result = control_service("MyAppService", "start")

    assert result.success is True
    run_mock.assert_called_once_with(["sc", "start", "MyAppService"])


def test_control_service_windows_restart_stops_then_starts():
    with (
        patch("agent.commands.current_os", return_value="windows"),
        patch("agent.commands._run", side_effect=[_completed(0), _completed(0)]) as run_mock,
    ):
        result = control_service("MyAppService", "restart")

    assert result.success is True
    assert run_mock.call_args_list[0].args[0] == ["sc", "stop", "MyAppService"]
    assert run_mock.call_args_list[1].args[0] == ["sc", "start", "MyAppService"]


def test_control_service_linux_uses_systemctl():
    with (
        patch("agent.commands.current_os", return_value="linux"),
        patch("agent.commands._run", return_value=_completed(0)) as run_mock,
    ):
        result = control_service("myapp", "restart")

    assert result.success is True
    run_mock.assert_called_once_with(["systemctl", "restart", "myapp"])


def test_control_service_reports_failure_from_nonzero_exit():
    with (
        patch("agent.commands.current_os", return_value="linux"),
        patch("agent.commands._run", return_value=_completed(5, stderr="Unit not found")),
    ):
        result = control_service("myapp", "start")

    assert result.success is False
    assert "Unit not found" in result.detail


# --- execute: dispatcher ---


def test_execute_kill_process_dispatches_correctly():
    with patch("agent.commands.kill_process", return_value=CommandResult(True, "ok")) as mock_kill:
        result = execute("kill_process", "kill", "1234")

    mock_kill.assert_called_once_with(1234)
    assert result.success is True


def test_execute_service_control_dispatches_correctly():
    with patch("agent.commands.control_service", return_value=CommandResult(True, "ok")) as mock_ctrl:
        result = execute("service_control", "restart", "MyApp")

    mock_ctrl.assert_called_once_with("MyApp", "restart")
    assert result.success is True


def test_execute_rejects_non_numeric_pid():
    result = execute("kill_process", "kill", "not-a-number")
    assert result.success is False
    assert "Geçersiz PID" in result.detail


def test_execute_rejects_unknown_command_type():
    result = execute("delete_files", "kill", "x")
    assert result.success is False


# --- Power control (reboot/shutdown/logoff) — GERÇEK bir reboot/shutdown
# ASLA test edilmez, `subprocess.run` her zaman mock'lanır. ---


def test_reboot_uses_short_delay_not_instant_on_windows():
    """`/t 0` DEĞİL kısa bir gecikme kullanılmalı — agent'ın sonucu
    bildirebilmesi için (bkz. modül docstring'i, gerçek bir kullanıcı
    isteğinden bilinçli sapma)."""
    with (
        patch("agent.commands.current_os", return_value="windows"),
        patch("agent.commands._run", return_value=_completed(0)) as run_mock,
    ):
        result = reboot()

    assert result.success is True
    args = run_mock.call_args.args[0]
    assert args[:2] == ["shutdown", "/r"]
    assert "0" not in args  # /t 0 DEĞİL


def test_reboot_uses_no_block_on_linux():
    with (
        patch("agent.commands.current_os", return_value="linux"),
        patch("agent.commands._run", return_value=_completed(0)) as run_mock,
    ):
        result = reboot()

    assert result.success is True
    run_mock.assert_called_once_with(["systemctl", "reboot", "--no-block"])


def test_shutdown_windows():
    with (
        patch("agent.commands.current_os", return_value="windows"),
        patch("agent.commands._run", return_value=_completed(0)) as run_mock,
    ):
        result = shutdown()

    assert result.success is True
    assert run_mock.call_args.args[0][:2] == ["shutdown", "/s"]


def test_shutdown_linux():
    with (
        patch("agent.commands.current_os", return_value="linux"),
        patch("agent.commands._run", return_value=_completed(0)) as run_mock,
    ):
        result = shutdown()

    assert result.success is True
    run_mock.assert_called_once_with(["systemctl", "poweroff", "--no-block"])


def test_shutdown_reports_failure_from_nonzero_exit():
    with (
        patch("agent.commands.current_os", return_value="windows"),
        patch("agent.commands._run", return_value=_completed(1, stderr="Access denied")),
    ):
        result = shutdown()

    assert result.success is False
    assert "Access denied" in result.detail


def test_logoff_windows_ignores_username():
    with (
        patch("agent.commands.current_os", return_value="windows"),
        patch("agent.commands._run", return_value=_completed(0)) as run_mock,
    ):
        result = logoff("some-user")

    assert result.success is True
    run_mock.assert_called_once_with(["logoff"])


def test_logoff_linux_requires_username():
    with patch("agent.commands.current_os", return_value="linux"):
        result = logoff(None)

    assert result.success is False
    assert "kullanıcı adı gerekli" in result.detail


def test_logoff_linux_uses_pkill_with_target_user():
    with (
        patch("agent.commands.current_os", return_value="linux"),
        patch("agent.commands._run", return_value=_completed(0)) as run_mock,
    ):
        result = logoff("alice")

    assert result.success is True
    run_mock.assert_called_once_with(["pkill", "-KILL", "-u", "alice"])


def test_control_power_dispatches_reboot():
    with patch("agent.commands.reboot", return_value=CommandResult(True, "ok")) as mock_reboot:
        result = control_power("reboot", "")

    mock_reboot.assert_called_once()
    assert result.success is True


def test_control_power_dispatches_shutdown():
    with patch("agent.commands.shutdown", return_value=CommandResult(True, "ok")) as mock_shutdown:
        result = control_power("shutdown", "")

    mock_shutdown.assert_called_once()
    assert result.success is True


def test_control_power_dispatches_logoff_with_target():
    with patch("agent.commands.logoff", return_value=CommandResult(True, "ok")) as mock_logoff:
        result = control_power("logoff", "alice")

    mock_logoff.assert_called_once_with("alice")
    assert result.success is True


def test_control_power_rejects_unknown_action():
    result = control_power("hibernate", "")
    assert result.success is False


def test_execute_power_control_dispatches_correctly():
    with patch("agent.commands.control_power", return_value=CommandResult(True, "ok")) as mock_power:
        result = execute("power_control", "reboot", "")

    mock_power.assert_called_once_with("reboot", "")
    assert result.success is True
