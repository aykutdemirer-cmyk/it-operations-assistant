"""Bellek telemetry — `psutil.virtual_memory()`."""

from __future__ import annotations

import logging

import psutil

logger = logging.getLogger("agent.collectors.memory")


def collect_memory() -> dict:
    try:
        vm = psutil.virtual_memory()
        return {
            "total_bytes": vm.total,
            "used_bytes": vm.used,
            "percent": vm.percent,
        }
    except Exception:
        logger.warning("Bellek bilgisi alınamadı", exc_info=True)
        return {"total_bytes": None, "used_bytes": None, "percent": None}
