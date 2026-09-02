"""`POST /api/agents/{id}/inventory` gövdesine (`apps/api/app/agents/
models.py::AgentInventoryRequest`) birebir uyan bir payload üretir —
SEYREK değişen veriler (donanım/OS/network/software/services/process).
Telemetry ile (`telemetry.py`) KARIŞTIRILMAZ, bkz. Faz 30 master prompt
§13."""

from __future__ import annotations

from datetime import datetime, timezone

from agent import SCHEMA_VERSION
from agent import platform as agent_platform
from agent.collectors import cpu, memory, network, processes as processes_collector, services, system


def build_inventory_payload(max_processes: int = 50) -> dict:
    host_info = system.collect_host_info()
    os_info = system.collect_os_info()
    os_info["boot_time"] = host_info["boot_time"]

    hardware = cpu.collect_cpu_hardware()
    hardware["total_memory_bytes"] = memory.collect_memory()["total_bytes"]
    try:
        hardware.update(agent_platform.resolve().hardware_info())
    except Exception:
        pass  # üretici/model bilgisi olmadan devam — kritik değil

    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "hardware": hardware,
        "os": os_info,
        "network_interfaces": network.collect_interfaces(),
        # Faz 30 MVP: kurulu yazılım envanteri KASITLI olarak boş —
        # güvenilir, cross-platform, root/yönetici gerektirmeyen bir
        # yöntem bu fazın kapsamı dışında bırakıldı (bkz. README "Bilinen
        # Sınırlar"). Uydurulmuş bir liste üretmek yerine dürüstçe boş.
        "software": [],
        "services": services.collect_services(),
        "processes": processes_collector.collect_processes(limit=max_processes),
    }
