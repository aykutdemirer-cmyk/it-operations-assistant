"""`agent/platform/windows.py` testleri. Gerçek Windows API'sine
bağımlı DEĞİL — `winreg`/`psutil` `sys.modules` üzerinden mock'lanır,
bu sayede testler Linux CI ortamında da (bkz. kullanıcı talimatı §30)
çalışır."""

import subprocess
import sys
from unittest.mock import MagicMock, patch

from agent.platform import windows


def test_machine_id_reads_registry_value():
    fake_key_context = MagicMock()
    fake_key_context.__enter__.return_value = MagicMock()
    fake_key_context.__exit__.return_value = False

    fake_winreg = MagicMock()
    fake_winreg.HKEY_LOCAL_MACHINE = "HKLM"
    fake_winreg.OpenKey.return_value = fake_key_context
    fake_winreg.QueryValueEx.return_value = ("guid-123", 1)

    with patch.dict(sys.modules, {"winreg": fake_winreg}):
        result = windows.machine_id()

    assert result == "guid-123"


def test_machine_id_returns_none_on_registry_error():
    fake_winreg = MagicMock()
    fake_winreg.OpenKey.side_effect = OSError("erişim reddedildi")

    with patch.dict(sys.modules, {"winreg": fake_winreg}):
        result = windows.machine_id()

    assert result is None


def test_list_services_normalizes_psutil_output():
    fake_service = MagicMock()
    fake_service.as_dict.return_value = {
        "name": "spooler", "display_name": "Print Spooler", "status": "running", "start_type": "auto",
    }
    fake_psutil = MagicMock()
    fake_psutil.win_service_iter.return_value = [fake_service]

    with patch.dict(sys.modules, {"psutil": fake_psutil}):
        result = windows.list_services()

    assert result == [{"name": "spooler", "display_name": "Print Spooler", "state": "running", "startup_type": "auto"}]


def test_list_services_skips_service_that_fails_to_read():
    good = MagicMock()
    good.as_dict.return_value = {"name": "ok", "display_name": "OK", "status": "running", "start_type": "auto"}
    bad = MagicMock()
    bad.as_dict.side_effect = RuntimeError("boom")

    fake_psutil = MagicMock()
    fake_psutil.win_service_iter.return_value = [good, bad]

    with patch.dict(sys.modules, {"psutil": fake_psutil}):
        result = windows.list_services()

    assert len(result) == 1
    assert result[0]["name"] == "ok"


def test_list_services_returns_empty_list_when_psutil_unavailable():
    fake_psutil = MagicMock()
    fake_psutil.win_service_iter.side_effect = RuntimeError("boom")

    with patch.dict(sys.modules, {"psutil": fake_psutil}):
        result = windows.list_services()

    assert result == []


def test_hardware_info_is_honestly_none_windows_has_no_wmi_dependency():
    result = windows.hardware_info()
    assert result == {"manufacturer": None, "model": None}


def _quser_fixture(rows: list[tuple[str, str, str, str, str, str]]) -> str:
    """Gerçek `quser` sabit-genişlikli çıktısını simüle eder (bkz.
    `windows.py::_QUSER_COLUMNS` — sütun genişlikleri burada
    KEYFİDİR, önemli olan header/veri satırlarının AYNI ofsetleri
    kullanması)."""
    header = " USERNAME".ljust(24) + "SESSIONNAME".ljust(21) + "ID".ljust(4) + "STATE".ljust(8) + "IDLE TIME".ljust(11) + "LOGON TIME"
    lines = [header]
    for marker, username, session_name, session_id, state, idle, logon_time in [
        (r[0], r[1], r[2], r[3], r[4], "", r[5]) for r in rows
    ]:
        row = (
            (marker + username).ljust(24)
            + session_name.ljust(21)
            + session_id.ljust(4)
            + state.ljust(8)
            + idle.ljust(11)
            + logon_time
        )
        lines.append(row)
    return "\n".join(lines) + "\n"


def test_list_sessions_parses_quser_output():
    fake_output = _quser_fixture(
        [(">", "administrator", "rdp-tcp#1", "2", "Active", "9/2/2026 8:57 AM")]
    )
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=fake_output, stderr="")

    with patch("agent.platform.windows.subprocess.run", return_value=fake_result):
        result = windows.list_sessions()

    assert result == [
        {
            "username": "administrator",
            "session_name": "rdp-tcp#1",
            "status": "active",
            "logon_time": "9/2/2026 8:57 AM",
        }
    ]


def test_list_sessions_normalizes_disconnected_status():
    fake_output = _quser_fixture([(" ", "bob", "", "3", "Disc", "9/1/2026 5:00 PM")])
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=fake_output, stderr="")

    with patch("agent.platform.windows.subprocess.run", return_value=fake_result):
        result = windows.list_sessions()

    assert result[0]["status"] == "disconnected"
    assert result[0]["session_name"] is None


def test_list_sessions_returns_empty_list_when_quser_missing():
    with patch("agent.platform.windows.subprocess.run", side_effect=FileNotFoundError("quser yok")):
        assert windows.list_sessions() == []


def test_list_sessions_returns_empty_list_when_no_sessions():
    fake_result = subprocess.CompletedProcess(args=[], returncode=1, stdout="No User exists for *\n", stderr="")
    with patch("agent.platform.windows.subprocess.run", return_value=fake_result):
        assert windows.list_sessions() == []


def test_list_sessions_returns_empty_list_on_unexpected_header():
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="garbage\nheader\n", stderr="")
    with patch("agent.platform.windows.subprocess.run", return_value=fake_result):
        assert windows.list_sessions() == []
