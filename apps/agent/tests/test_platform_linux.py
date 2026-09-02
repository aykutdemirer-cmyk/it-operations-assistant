"""`agent/platform/linux.py` testleri — gerçek dosya sistemi/`systemctl`
çağrısı YOK, `open`/`subprocess.run` mock'lanır."""

import subprocess
from unittest.mock import mock_open, patch

from agent.platform import linux


def test_machine_id_reads_etc_machine_id():
    with patch("builtins.open", mock_open(read_data="abc123\n")):
        assert linux.machine_id() == "abc123"


def test_machine_id_falls_back_to_dbus_path_when_first_missing():
    calls = {"count": 0}

    def _open(path, *args, **kwargs):
        calls["count"] += 1
        if path == "/etc/machine-id":
            raise OSError("yok")
        return mock_open(read_data="dbus-machine-id\n").return_value

    with patch("builtins.open", side_effect=_open):
        assert linux.machine_id() == "dbus-machine-id"


def test_machine_id_returns_none_when_nothing_readable():
    with patch("builtins.open", side_effect=OSError("yok")):
        assert linux.machine_id() is None


def test_list_services_parses_systemctl_output():
    fake_output = "sshd.service loaded active running\ncron.service loaded active running\n"
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=fake_output, stderr="")

    with patch("agent.platform.linux.subprocess.run", return_value=fake_result):
        result = linux.list_services()

    assert result == [
        {"name": "sshd.service", "display_name": None, "state": "active/running", "startup_type": "loaded"},
        {"name": "cron.service", "display_name": None, "state": "active/running", "startup_type": "loaded"},
    ]


def test_list_services_returns_empty_list_when_systemctl_missing():
    with patch("agent.platform.linux.subprocess.run", side_effect=FileNotFoundError("systemctl yok")):
        assert linux.list_services() == []


def test_list_services_returns_empty_list_on_timeout():
    with patch("agent.platform.linux.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="systemctl", timeout=5)):
        assert linux.list_services() == []


def test_list_sessions_parses_who_output():
    fake_output = "alice    pts/0        2026-09-02 08:57 (10.0.213.1)\n"
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=fake_output, stderr="")

    with patch("agent.platform.linux.subprocess.run", return_value=fake_result):
        result = linux.list_sessions()

    assert result == [
        {"username": "alice", "session_name": "pts/0", "status": "active", "logon_time": "2026-09-02 08:57"}
    ]


def test_list_sessions_returns_empty_list_when_who_missing():
    with patch("agent.platform.linux.subprocess.run", side_effect=FileNotFoundError("who yok")):
        assert linux.list_sessions() == []


def test_list_sessions_returns_empty_list_when_no_one_logged_in():
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("agent.platform.linux.subprocess.run", return_value=fake_result):
        assert linux.list_sessions() == []


def test_hardware_info_reads_dmi_sysfs():
    def _open(path, *args, **kwargs):
        if path.endswith("sys_vendor"):
            return mock_open(read_data="VMware, Inc.\n").return_value
        if path.endswith("product_name"):
            return mock_open(read_data="VMware Virtual Platform\n").return_value
        raise OSError("yok")

    with patch("builtins.open", side_effect=_open):
        result = linux.hardware_info()

    assert result == {"manufacturer": "VMware, Inc.", "model": "VMware Virtual Platform"}


def test_hardware_info_survives_missing_dmi_files():
    with patch("builtins.open", side_effect=OSError("yok")):
        result = linux.hardware_info()
    assert result == {"manufacturer": None, "model": None}
