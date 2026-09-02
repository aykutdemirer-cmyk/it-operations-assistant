"""`POST /api/agents/heartbeat` gövdesini üretir. `uptime_seconds` —
agent SÜRECİNİN kendi çalışma süresidir (host'un OS uptime'ı DEĞİL;
o, `inventory.py`'nin `os.boot_time`/`system.collect_host_info`
alanında ayrıca taşınır) — heartbeat, "agent canlı mı" sorusuna cevap
verir, host'un ne kadar süredir açık olduğuna değil."""

from __future__ import annotations

import time

from agent import __version__


def build_heartbeat_payload(agent_started_at: float) -> dict:
    return {
        "uptime_seconds": max(0.0, time.time() - agent_started_at),
        "agent_version": __version__,
    }
