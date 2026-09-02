"""`POST /api/agents/{id}/telemetry` gövdesine (`apps/api/app/agents/
models.py::AgentTelemetryRequest`) birebir uyan bir payload üretir —
SIK değişen veriler (CPU/RAM/disk/network). Envanterle (`inventory.py`)
KARIŞTIRILMAZ, bkz. Faz 30 master prompt §13."""

from __future__ import annotations

from datetime import datetime, timezone

from agent import SCHEMA_VERSION
from agent.collectors import cpu, disk, memory, network, sessions as sessions_collector


def build_telemetry_payload() -> dict:
    memory_info = memory.collect_memory()
    session_list = sessions_collector.collect_sessions()
    last_logged_in_user, active_sessions_count = sessions_collector.summarize_sessions(session_list)
    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "cpu_percent": cpu.collect_cpu_usage(),
        "memory_total_bytes": memory_info["total_bytes"],
        "memory_used_bytes": memory_info["used_bytes"],
        "memory_percent": memory_info["percent"],
        "disks": disk.collect_disks(),
        "network_interfaces": network.collect_interfaces(),
        # Faz 34 — User Sessions Tracking.
        "sessions": session_list,
        "last_logged_in_user": last_logged_in_user,
        "active_sessions_count": active_sessions_count,
    }
