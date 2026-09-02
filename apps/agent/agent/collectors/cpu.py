"""CPU envanteri (model/çekirdek sayısı) ve telemetry (kullanım %,
yalnızca Linux'ta load average)."""

from __future__ import annotations

import logging
import os
import platform as _stdlib_platform

import psutil

logger = logging.getLogger("agent.collectors.cpu")


def collect_cpu_usage(interval: float = 0.5) -> float | None:
    """Anlık CPU kullanım yüzdesi. `interval` kadar örnekler — psutil'in
    önerdiği doğru kullanım şekli (`interval=None` ilk çağrıda yanıltıcı
    `0.0` dönebilir, bkz. psutil dokümantasyonu)."""
    try:
        return psutil.cpu_percent(interval=interval)
    except Exception:
        logger.warning("CPU kullanımı alınamadı", exc_info=True)
        return None


def collect_cpu_hardware() -> dict:
    try:
        logical = psutil.cpu_count(logical=True)
        physical = psutil.cpu_count(logical=False)
    except Exception:
        logger.warning("CPU çekirdek sayısı alınamadı", exc_info=True)
        logical = physical = None

    return {
        "cpu_model": _cpu_model(),
        "cpu_cores": physical,
        "cpu_logical_processors": logical,
    }


def collect_load_average() -> list[float] | None:
    """Yalnızca Linux/Unix'te anlamlı — Windows'ta `os.getloadavg` hiç
    YOK, `None` döner (Windows için uydurulmuş bir değer üretilmez)."""
    if not hasattr(os, "getloadavg"):
        return None
    try:
        return list(os.getloadavg())
    except OSError:
        return None


def _cpu_model() -> str | None:
    if _stdlib_platform.system() == "Windows":
        return _stdlib_platform.processor() or None
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return _stdlib_platform.processor() or None
