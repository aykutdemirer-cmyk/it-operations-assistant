from unittest.mock import patch

from agent import __version__
from agent.heartbeat import build_heartbeat_payload


def test_build_heartbeat_payload_includes_uptime_and_version():
    with patch("agent.heartbeat.time.time", return_value=1000.0):
        payload = build_heartbeat_payload(agent_started_at=940.0)

    assert payload["uptime_seconds"] == 60.0
    assert payload["agent_version"] == __version__


def test_build_heartbeat_payload_never_negative_uptime():
    """Saat geri alınırsa (nadiren) bile negatif bir uptime uydurulmaz."""
    with patch("agent.heartbeat.time.time", return_value=100.0):
        payload = build_heartbeat_payload(agent_started_at=500.0)

    assert payload["uptime_seconds"] == 0.0
