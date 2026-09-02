from unittest.mock import patch

from agent import SCHEMA_VERSION
from agent.telemetry import build_telemetry_payload


def test_build_telemetry_payload_has_expected_shape():
    with patch("agent.telemetry.cpu.collect_cpu_usage", return_value=12.3):
        with patch("agent.telemetry.memory.collect_memory", return_value={"total_bytes": 100, "used_bytes": 50, "percent": 50.0}):
            with patch("agent.telemetry.disk.collect_disks", return_value=[]):
                with patch("agent.telemetry.network.collect_interfaces", return_value=[]):
                    with patch(
                        "agent.telemetry.sessions_collector.collect_sessions",
                        return_value=[{"username": "admin", "session_name": "console", "status": "active", "logon_time": None}],
                    ):
                        payload = build_telemetry_payload()

    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["cpu_percent"] == 12.3
    assert payload["memory_total_bytes"] == 100
    assert payload["memory_used_bytes"] == 50
    assert payload["memory_percent"] == 50.0
    assert payload["disks"] == []
    assert payload["network_interfaces"] == []
    assert "collected_at" in payload
    # Faz 34 — User Sessions Tracking.
    assert payload["sessions"] == [{"username": "admin", "session_name": "console", "status": "active", "logon_time": None}]
    assert payload["last_logged_in_user"] == "admin"
    assert payload["active_sessions_count"] == 1


def test_build_telemetry_payload_honest_when_no_sessions():
    with patch("agent.telemetry.cpu.collect_cpu_usage", return_value=None):
        with patch("agent.telemetry.memory.collect_memory", return_value={"total_bytes": None, "used_bytes": None, "percent": None}):
            with patch("agent.telemetry.disk.collect_disks", return_value=[]):
                with patch("agent.telemetry.network.collect_interfaces", return_value=[]):
                    with patch("agent.telemetry.sessions_collector.collect_sessions", return_value=[]):
                        payload = build_telemetry_payload()

    assert payload["sessions"] == []
    assert payload["last_logged_in_user"] is None
    assert payload["active_sessions_count"] == 0


def test_build_telemetry_payload_never_includes_processes_or_services():
    """Telemetry ≠ Inventory — süreç/servis bilgisi burada asla yer
    almaz (bkz. `docs/decisions.md`, §13 kullanıcı talimatı)."""
    with patch("agent.telemetry.cpu.collect_cpu_usage", return_value=None):
        with patch("agent.telemetry.memory.collect_memory", return_value={"total_bytes": None, "used_bytes": None, "percent": None}):
            with patch("agent.telemetry.disk.collect_disks", return_value=[]):
                with patch("agent.telemetry.network.collect_interfaces", return_value=[]):
                    with patch("agent.telemetry.sessions_collector.collect_sessions", return_value=[]):
                        payload = build_telemetry_payload()

    assert "processes" not in payload
    assert "services" not in payload
    assert "software" not in payload
