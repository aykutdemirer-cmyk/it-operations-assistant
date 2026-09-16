"""`agent/lifecycle.py` için testler (Agent Lifecycle Management —
Uzaktan Silme/Uzaktan Güncelleme). Gerçek bir servis ASLA
durdurulmaz/silinmez, gerçek bir HTTP indirmesi ASLA yapılmaz —
`subprocess.run`/`subprocess.Popen`/`urllib.request.urlopen` hep
mock'lanır."""

import io
import subprocess
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from agent import lifecycle


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _fake_zip_bytes(exe_content: bytes = b"fake-exe-bytes") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("itops-agent.exe", exe_content)
        zf.writestr("install_windows_service.ps1", "# script")
        zf.writestr("README.txt", "readme")
    return buf.getvalue()


# --- uninstall_service ---


def test_uninstall_service_rejected_on_non_windows():
    with patch("agent.lifecycle.current_os", return_value="linux"):
        result = lifecycle.uninstall_service()
    assert result.success is False
    assert "Windows" in result.detail


def test_uninstall_service_stops_and_deletes_on_windows():
    with (
        patch("agent.lifecycle.current_os", return_value="windows"),
        patch("agent.lifecycle.subprocess.run", return_value=_completed(0)) as run_mock,
    ):
        result = lifecycle.uninstall_service()

    assert result.success is True
    calls = [call.args[0] for call in run_mock.call_args_list]
    assert ["sc", "stop", "ITOpsAgent"] in calls
    assert ["sc", "delete", "ITOpsAgent"] in calls


def test_uninstall_service_reports_failure_when_delete_fails():
    with (
        patch("agent.lifecycle.current_os", return_value="windows"),
        patch("agent.lifecycle.subprocess.run", return_value=_completed(1, stderr="access denied")),
    ):
        result = lifecycle.uninstall_service()

    assert result.success is False
    assert "access denied" in result.detail


def test_uninstall_service_never_raises_when_command_fails_to_start():
    with (
        patch("agent.lifecycle.current_os", return_value="windows"),
        patch("agent.lifecycle.subprocess.run", side_effect=OSError("sc.exe not found")),
    ):
        result = lifecycle.uninstall_service()

    assert result.success is False
    assert "çalıştırılamadı" in result.detail


# --- update_self ---


def test_update_self_rejected_on_non_windows():
    with patch("agent.lifecycle.current_os", return_value="linux"):
        result = lifecycle.update_self("http://backend:8000")
    assert result.success is False
    assert "Windows" in result.detail


def test_update_self_rejected_when_not_frozen():
    with (
        patch("agent.lifecycle.current_os", return_value="windows"),
        patch("agent.lifecycle.sys.frozen", False, create=True),
    ):
        result = lifecycle.update_self("http://backend:8000")
    assert result.success is False
    assert "paketlenmiş" in result.detail


def test_update_self_downloads_extracts_and_spawns_helper(tmp_path):
    fake_exe_path = tmp_path / "itops-agent.exe"
    fake_exe_path.write_bytes(b"old-exe")
    fake_response = MagicMock()
    fake_response.read.return_value = _fake_zip_bytes()
    fake_response.__enter__ = MagicMock(return_value=fake_response)
    fake_response.__exit__ = MagicMock(return_value=False)

    with (
        patch("agent.lifecycle.current_os", return_value="windows"),
        patch("agent.lifecycle.sys.frozen", True, create=True),
        patch("agent.lifecycle.sys.executable", str(fake_exe_path)),
        patch("agent.lifecycle.urllib.request.urlopen", return_value=fake_response) as urlopen_mock,
        patch("agent.lifecycle._spawn_update_helper") as spawn_mock,
    ):
        result = lifecycle.update_self("http://backend:8000")

    assert result.success is True
    urlopen_mock.assert_called_once()
    assert urlopen_mock.call_args.args[0] == "http://backend:8000/api/agents/download/windows-service"
    spawn_mock.assert_called_once()
    new_exe_arg = spawn_mock.call_args.args[1]
    assert new_exe_arg.name == "itops-agent.new.exe"
    assert new_exe_arg.read_bytes() == b"fake-exe-bytes"


def test_update_self_strips_trailing_slash_from_backend_url(tmp_path):
    fake_exe_path = tmp_path / "itops-agent.exe"
    fake_exe_path.write_bytes(b"old-exe")
    fake_response = MagicMock()
    fake_response.read.return_value = _fake_zip_bytes()
    fake_response.__enter__ = MagicMock(return_value=fake_response)
    fake_response.__exit__ = MagicMock(return_value=False)

    with (
        patch("agent.lifecycle.current_os", return_value="windows"),
        patch("agent.lifecycle.sys.frozen", True, create=True),
        patch("agent.lifecycle.sys.executable", str(fake_exe_path)),
        patch("agent.lifecycle.urllib.request.urlopen", return_value=fake_response) as urlopen_mock,
        patch("agent.lifecycle._spawn_update_helper"),
    ):
        lifecycle.update_self("http://backend:8000/")

    assert urlopen_mock.call_args.args[0] == "http://backend:8000/api/agents/download/windows-service"


def test_update_self_reports_failure_when_download_fails(tmp_path):
    fake_exe_path = tmp_path / "itops-agent.exe"
    fake_exe_path.write_bytes(b"old-exe")

    with (
        patch("agent.lifecycle.current_os", return_value="windows"),
        patch("agent.lifecycle.sys.frozen", True, create=True),
        patch("agent.lifecycle.sys.executable", str(fake_exe_path)),
        patch("agent.lifecycle.urllib.request.urlopen", side_effect=OSError("connection refused")),
    ):
        result = lifecycle.update_self("http://backend:8000")

    assert result.success is False
    assert "indirilemedi" in result.detail


def test_update_self_reports_failure_when_zip_has_no_exe(tmp_path):
    fake_exe_path = tmp_path / "itops-agent.exe"
    fake_exe_path.write_bytes(b"old-exe")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("README.txt", "no exe here")
    fake_response = MagicMock()
    fake_response.read.return_value = buf.getvalue()
    fake_response.__enter__ = MagicMock(return_value=fake_response)
    fake_response.__exit__ = MagicMock(return_value=False)

    with (
        patch("agent.lifecycle.current_os", return_value="windows"),
        patch("agent.lifecycle.sys.frozen", True, create=True),
        patch("agent.lifecycle.sys.executable", str(fake_exe_path)),
        patch("agent.lifecycle.urllib.request.urlopen", return_value=fake_response),
    ):
        result = lifecycle.update_self("http://backend:8000")

    assert result.success is False
    assert "indirilemedi" in result.detail


def test_update_self_reports_failure_when_helper_spawn_fails(tmp_path):
    fake_exe_path = tmp_path / "itops-agent.exe"
    fake_exe_path.write_bytes(b"old-exe")
    fake_response = MagicMock()
    fake_response.read.return_value = _fake_zip_bytes()
    fake_response.__enter__ = MagicMock(return_value=fake_response)
    fake_response.__exit__ = MagicMock(return_value=False)

    with (
        patch("agent.lifecycle.current_os", return_value="windows"),
        patch("agent.lifecycle.sys.frozen", True, create=True),
        patch("agent.lifecycle.sys.executable", str(fake_exe_path)),
        patch("agent.lifecycle.urllib.request.urlopen", return_value=fake_response),
        patch("agent.lifecycle._spawn_update_helper", side_effect=OSError("cannot spawn")),
    ):
        result = lifecycle.update_self("http://backend:8000")

    assert result.success is False
    assert "başlatılamadı" in result.detail


def test_spawn_update_helper_never_touches_real_process(tmp_path):
    """`subprocess.Popen`'ın GERÇEKTEN çağrıldığını doğrular ama hiçbir
    gerçek PowerShell süreci başlatılmaz (mock'lanır)."""
    exe_path = tmp_path / "itops-agent.exe"
    new_exe_path = tmp_path / "itops-agent.new.exe"

    with (
        patch("agent.lifecycle.subprocess.Popen") as popen_mock,
        patch("agent.lifecycle.tempfile.gettempdir", return_value=str(tmp_path)),
    ):
        lifecycle._spawn_update_helper(exe_path, new_exe_path)

    popen_mock.assert_called_once()
    args = popen_mock.call_args.args[0]
    assert args[0] == "powershell"
    script_path = tmp_path / "itops-agent-update.ps1"
    assert script_path.exists()
    content = script_path.read_text(encoding="ascii")
    assert "sc.exe stop ITOpsAgent" in content
    assert "sc.exe start ITOpsAgent" in content
    assert str(new_exe_path) in content
    assert str(exe_path) in content


# --- commands.execute() dispatch (widened for Lifecycle Management) ---


def test_execute_dispatches_uninstall_service():
    from agent.commands import CommandResult, execute

    with patch("agent.lifecycle.uninstall_service", return_value=CommandResult(True, "ok")) as mock:
        result = execute("uninstall_service", "uninstall", "self")

    mock.assert_called_once()
    assert result.success is True


def test_execute_dispatches_update_self_with_backend_url():
    from agent.commands import CommandResult, execute

    with patch("agent.lifecycle.update_self", return_value=CommandResult(True, "ok")) as mock:
        result = execute("update_self", "update", "self", backend_url="http://backend:8000")

    mock.assert_called_once_with("http://backend:8000")
    assert result.success is True


def test_execute_update_self_fails_without_backend_url():
    from agent.commands import execute

    result = execute("update_self", "update", "self")

    assert result.success is False
    assert "backend_url" in result.detail
