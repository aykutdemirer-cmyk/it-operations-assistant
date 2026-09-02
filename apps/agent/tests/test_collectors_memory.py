from types import SimpleNamespace
from unittest.mock import patch

from agent.collectors import memory


def test_collect_memory_returns_normalized_fields():
    fake_vm = SimpleNamespace(total=16_000_000_000, used=8_000_000_000, percent=50.0)
    with patch("agent.collectors.memory.psutil.virtual_memory", return_value=fake_vm):
        result = memory.collect_memory()

    assert result == {"total_bytes": 16_000_000_000, "used_bytes": 8_000_000_000, "percent": 50.0}


def test_collect_memory_survives_failure():
    with patch("agent.collectors.memory.psutil.virtual_memory", side_effect=RuntimeError("boom")):
        result = memory.collect_memory()
    assert result == {"total_bytes": None, "used_bytes": None, "percent": None}
