from unittest.mock import patch

from agent.collectors import cpu


def test_collect_cpu_usage_returns_percentage():
    with patch("agent.collectors.cpu.psutil.cpu_percent", return_value=42.5):
        assert cpu.collect_cpu_usage() == 42.5


def test_collect_cpu_usage_returns_none_on_failure():
    with patch("agent.collectors.cpu.psutil.cpu_percent", side_effect=RuntimeError("boom")):
        assert cpu.collect_cpu_usage() is None


def test_collect_cpu_hardware_returns_core_counts():
    with patch("agent.collectors.cpu.psutil.cpu_count", side_effect=lambda logical: 16 if logical else 8):
        with patch("agent.collectors.cpu._cpu_model", return_value="Intel Xeon"):
            result = cpu.collect_cpu_hardware()

    assert result == {"cpu_model": "Intel Xeon", "cpu_cores": 8, "cpu_logical_processors": 16}


def test_collect_cpu_hardware_survives_failure():
    with patch("agent.collectors.cpu.psutil.cpu_count", side_effect=RuntimeError("boom")):
        result = cpu.collect_cpu_hardware()
    assert result["cpu_cores"] is None
    assert result["cpu_logical_processors"] is None


def test_collect_load_average_none_when_unsupported():
    with patch("agent.collectors.cpu.os") as fake_os:
        del fake_os.getloadavg  # hasattr() False döndürür
        assert cpu.collect_load_average() is None


def test_collect_load_average_returns_list_when_supported():
    with patch("agent.collectors.cpu.os.getloadavg", return_value=(0.5, 0.7, 0.9), create=True):
        result = cpu.collect_load_average()
    assert result == [0.5, 0.7, 0.9]
