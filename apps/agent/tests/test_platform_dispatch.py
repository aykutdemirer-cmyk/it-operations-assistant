from unittest.mock import patch

import pytest

from agent import platform as agent_platform


def test_current_os_detects_windows():
    with patch("agent.platform.sys.platform", "win32"):
        assert agent_platform.current_os() == "windows"


def test_current_os_detects_linux():
    with patch("agent.platform.sys.platform", "linux"):
        assert agent_platform.current_os() == "linux"


def test_current_os_raises_for_unsupported_platform():
    with patch("agent.platform.sys.platform", "darwin"):
        with pytest.raises(RuntimeError):
            agent_platform.current_os()


def test_resolve_returns_windows_module():
    with patch("agent.platform.sys.platform", "win32"):
        module = agent_platform.resolve()
    assert module.__name__ == "agent.platform.windows"


def test_resolve_returns_linux_module():
    with patch("agent.platform.sys.platform", "linux"):
        module = agent_platform.resolve()
    assert module.__name__ == "agent.platform.linux"
