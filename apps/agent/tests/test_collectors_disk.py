from types import SimpleNamespace
from unittest.mock import patch

from agent.collectors import disk


def _partition(device, mountpoint):
    return SimpleNamespace(device=device, mountpoint=mountpoint)


def test_collect_disks_returns_usage_per_partition():
    partitions = [_partition("/dev/sda1", "/")]
    usage = SimpleNamespace(total=100, used=40, free=60, percent=40.0)

    with patch("agent.collectors.disk.psutil.disk_partitions", return_value=partitions):
        with patch("agent.collectors.disk.psutil.disk_usage", return_value=usage):
            result = disk.collect_disks()

    assert result == [{"device": "/dev/sda1", "total_bytes": 100, "used_bytes": 40, "free_bytes": 60, "percent": 40.0}]


def test_collect_disks_skips_unreadable_partition_without_crashing():
    partitions = [_partition("/dev/sda1", "/"), _partition("/dev/sr0", "/mnt/cdrom")]

    def _usage(mountpoint):
        if mountpoint == "/mnt/cdrom":
            raise PermissionError("no disk")
        return SimpleNamespace(total=100, used=40, free=60, percent=40.0)

    with patch("agent.collectors.disk.psutil.disk_partitions", return_value=partitions):
        with patch("agent.collectors.disk.psutil.disk_usage", side_effect=_usage):
            result = disk.collect_disks()

    assert len(result) == 1
    assert result[0]["device"] == "/dev/sda1"


def test_collect_disks_returns_empty_list_when_partitions_unavailable():
    with patch("agent.collectors.disk.psutil.disk_partitions", side_effect=RuntimeError("boom")):
        assert disk.collect_disks() == []
