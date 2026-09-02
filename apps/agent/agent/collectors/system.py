"""Host/OS envanteri — hostname/FQDN/makine kimliği/boot time/uptime ve
OS adı/versiyonu/kernel/mimarisi. Platform-özel kısım (`machine_id`)
`agent/platform/{windows,linux}.py`'ye devredilir; hiçbir toplama
adımı BAŞARISIZ olduğunda agent'ı çökertmez — eksik alan `None` kalır."""

from __future__ import annotations

import logging
import platform as _stdlib_platform
import socket
import time
from datetime import datetime, timezone

import psutil

from agent import platform as agent_platform

logger = logging.getLogger("agent.collectors.system")


def collect_host_info() -> dict:
    try:
        hostname = socket.gethostname()
    except OSError:
        logger.warning("hostname alınamadı", exc_info=True)
        hostname = "unknown"

    try:
        fqdn = socket.getfqdn()
    except OSError:
        fqdn = hostname

    boot_time_iso: str | None = None
    uptime_seconds: float | None = None
    try:
        boot_timestamp = psutil.boot_time()
        boot_time_iso = datetime.fromtimestamp(boot_timestamp, tz=timezone.utc).isoformat()
        uptime_seconds = max(0.0, time.time() - boot_timestamp)
    except Exception:
        logger.warning("boot_time alınamadı", exc_info=True)

    machine_id: str | None = None
    try:
        machine_id = agent_platform.resolve().machine_id()
    except Exception:
        logger.debug("machine_id alınamadı", exc_info=True)

    return {
        "hostname": hostname,
        "fqdn": fqdn,
        "machine_id": machine_id,
        "boot_time": boot_time_iso,
        "uptime_seconds": uptime_seconds,
    }


def collect_os_info() -> dict:
    """`apps/api/app/agents/models.py::OSInfo` ile aynı alan adları
    (name/version/kernel/architecture) — backend'e gönderilirken bire
    bir eşlenebilsin diye."""
    return {
        "name": _stdlib_platform.system() or None,
        "version": _stdlib_platform.version() or None,
        "kernel": _stdlib_platform.release() or None,
        "architecture": _stdlib_platform.machine() or None,
    }
