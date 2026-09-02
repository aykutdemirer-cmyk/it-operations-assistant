"""Disk envanteri/telemetry — her mount noktası için ayrı örnek
(`apps/api/app/agents/models.py::DiskSample` ile birebir alan adları)."""

from __future__ import annotations

import logging

import psutil

logger = logging.getLogger("agent.collectors.disk")


def collect_disks() -> list[dict]:
    disks: list[dict] = []
    try:
        partitions = psutil.disk_partitions(all=False)
    except Exception:
        logger.warning("Disk partition listesi alınamadı", exc_info=True)
        return disks

    for part in partitions:
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            # Bazı mount noktaları (ör. bağlı olmayan CD-ROM sürücüsü,
            # erişim izni olmayan network mount) okunamayabilir — bu tek
            # partition atlanır, diğerleri etkilenmez.
            continue
        disks.append(
            {
                "device": part.device or part.mountpoint,
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "percent": usage.percent,
            }
        )
    return disks
