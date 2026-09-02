from unittest.mock import MagicMock, patch

from agent.collectors import services


def test_collect_services_delegates_to_platform_module():
    fake_platform = MagicMock()
    fake_platform.list_services.return_value = [{"name": "spooler", "display_name": "Print Spooler", "state": "running", "startup_type": "auto"}]

    with patch("agent.collectors.services.agent_platform.resolve", return_value=fake_platform):
        result = services.collect_services()

    assert result == [{"name": "spooler", "display_name": "Print Spooler", "state": "running", "startup_type": "auto"}]


def test_collect_services_returns_empty_list_when_platform_module_raises():
    with patch("agent.collectors.services.agent_platform.resolve", side_effect=RuntimeError("boom")):
        assert services.collect_services() == []
