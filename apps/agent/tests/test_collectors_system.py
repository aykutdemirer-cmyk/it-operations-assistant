from unittest.mock import MagicMock, patch

from agent.collectors import system


def test_collect_host_info_returns_hostname_and_uptime():
    with patch("agent.collectors.system.socket.gethostname", return_value="myhost"):
        with patch("agent.collectors.system.socket.getfqdn", return_value="myhost.local"):
            with patch("agent.collectors.system.psutil.boot_time", return_value=1_700_000_000.0):
                with patch("agent.collectors.system.time.time", return_value=1_700_010_000.0):
                    fake_platform_module = MagicMock()
                    fake_platform_module.machine_id.return_value = "machine-uuid-123"
                    with patch("agent.collectors.system.agent_platform.resolve", return_value=fake_platform_module):
                        result = system.collect_host_info()

    assert result["hostname"] == "myhost"
    assert result["fqdn"] == "myhost.local"
    assert result["machine_id"] == "machine-uuid-123"
    assert result["boot_time"] is not None
    assert result["uptime_seconds"] == 10_000.0


def test_collect_host_info_survives_hostname_failure():
    with patch("agent.collectors.system.socket.gethostname", side_effect=OSError("boom")):
        result = system.collect_host_info()
    assert result["hostname"] == "unknown"


def test_collect_host_info_survives_machine_id_failure():
    with patch("agent.collectors.system.socket.gethostname", return_value="h"):
        with patch("agent.collectors.system.socket.getfqdn", return_value="h"):
            with patch("agent.collectors.system.agent_platform.resolve", side_effect=RuntimeError("boom")):
                result = system.collect_host_info()
    assert result["machine_id"] is None


def test_collect_os_info_returns_expected_keys():
    result = system.collect_os_info()
    assert set(result.keys()) == {"name", "version", "kernel", "architecture"}
