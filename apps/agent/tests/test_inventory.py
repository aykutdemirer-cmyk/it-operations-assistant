from unittest.mock import patch

from agent import SCHEMA_VERSION
from agent.inventory import build_inventory_payload


def _patch_all(**overrides):
    defaults = dict(
        host_info={"hostname": "h", "fqdn": "h", "machine_id": "m1", "boot_time": "2026-01-01T00:00:00+00:00", "uptime_seconds": 10.0},
        os_info={"name": "Linux", "version": "1.0", "kernel": "6.0", "architecture": "x86_64"},
        cpu_hardware={"cpu_model": "Intel", "cpu_cores": 4, "cpu_logical_processors": 8},
        memory={"total_bytes": 100, "used_bytes": 50, "percent": 50.0},
        interfaces=[],
        services=[{"name": "sshd.service", "display_name": None, "state": "active/running", "startup_type": "loaded"}],
        processes=[{"pid": 1, "name": "init", "cpu_percent": 0.1, "memory_percent": 0.1, "username": "root", "status": "running"}],
        hardware_info={"manufacturer": "VMware, Inc.", "model": "VMware Virtual Platform"},
    )
    defaults.update(overrides)
    return defaults


def test_build_inventory_payload_has_expected_shape():
    values = _patch_all()
    fake_platform_module = type("M", (), {"hardware_info": staticmethod(lambda: values["hardware_info"])})()

    with patch("agent.inventory.system.collect_host_info", return_value=values["host_info"]):
        with patch("agent.inventory.system.collect_os_info", return_value=values["os_info"]):
            with patch("agent.inventory.cpu.collect_cpu_hardware", return_value=values["cpu_hardware"]):
                with patch("agent.inventory.memory.collect_memory", return_value=values["memory"]):
                    with patch("agent.inventory.network.collect_interfaces", return_value=values["interfaces"]):
                        with patch("agent.inventory.services.collect_services", return_value=values["services"]):
                            with patch("agent.inventory.processes_collector.collect_processes", return_value=values["processes"]):
                                with patch("agent.inventory.agent_platform.resolve", return_value=fake_platform_module):
                                    payload = build_inventory_payload()

    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["hardware"]["cpu_model"] == "Intel"
    assert payload["hardware"]["total_memory_bytes"] == 100
    assert payload["hardware"]["manufacturer"] == "VMware, Inc."
    assert payload["os"]["boot_time"] == values["host_info"]["boot_time"]
    assert payload["services"] == values["services"]
    assert payload["processes"] == values["processes"]
    assert payload["software"] == []  # Faz 30 MVP — bilinçli olarak boş
    assert "collected_at" in payload


def test_build_inventory_payload_survives_platform_hardware_info_failure():
    values = _patch_all()
    with patch("agent.inventory.system.collect_host_info", return_value=values["host_info"]):
        with patch("agent.inventory.system.collect_os_info", return_value=values["os_info"]):
            with patch("agent.inventory.cpu.collect_cpu_hardware", return_value=values["cpu_hardware"]):
                with patch("agent.inventory.memory.collect_memory", return_value=values["memory"]):
                    with patch("agent.inventory.network.collect_interfaces", return_value=values["interfaces"]):
                        with patch("agent.inventory.services.collect_services", return_value=values["services"]):
                            with patch("agent.inventory.processes_collector.collect_processes", return_value=values["processes"]):
                                with patch("agent.inventory.agent_platform.resolve", side_effect=RuntimeError("boom")):
                                    payload = build_inventory_payload()

    # hardware_info() başarısız olsa bile inventory çökmez, geri kalan alanlar korunur
    assert payload["hardware"]["cpu_model"] == "Intel"


def test_build_inventory_payload_respects_max_processes():
    values = _patch_all()
    with patch("agent.inventory.system.collect_host_info", return_value=values["host_info"]):
        with patch("agent.inventory.system.collect_os_info", return_value=values["os_info"]):
            with patch("agent.inventory.cpu.collect_cpu_hardware", return_value=values["cpu_hardware"]):
                with patch("agent.inventory.memory.collect_memory", return_value=values["memory"]):
                    with patch("agent.inventory.network.collect_interfaces", return_value=values["interfaces"]):
                        with patch("agent.inventory.services.collect_services", return_value=values["services"]):
                            with patch(
                                "agent.inventory.processes_collector.collect_processes"
                            ) as mock_collect:
                                mock_collect.return_value = []
                                with patch("agent.inventory.agent_platform.resolve", side_effect=RuntimeError("boom")):
                                    build_inventory_payload(max_processes=7)

    mock_collect.assert_called_once_with(limit=7)
