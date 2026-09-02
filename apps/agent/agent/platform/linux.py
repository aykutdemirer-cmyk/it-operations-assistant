"""Yalnızca Linux'a özgü toplama mantığı."""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger("agent.platform.linux")

_MACHINE_ID_PATHS = ("/etc/machine-id", "/var/lib/dbus/machine-id")


def machine_id() -> str | None:
    """`/etc/machine-id` (systemd standardı) — yoksa D-Bus'un eski
    konumuna düşülür. İkisi de yoksa `None` (uydurulmaz)."""
    for path in _MACHINE_ID_PATHS:
        try:
            with open(path, encoding="utf-8") as f:
                value = f.read().strip()
                if value:
                    return value
        except OSError:
            continue
    return None


def hardware_info() -> dict:
    """`/sys/class/dmi/id/*` — çoğu Linux dağıtımında root gerekmeden
    okunabilir (sanal makinelerde de genelde hipervizör bilgisini
    verir, ör. "VMware, Inc."). Okunamazsa alan `None` kalır, agent
    ÇÖKMEZ."""
    return {
        "manufacturer": _read_dmi("sys_vendor"),
        "model": _read_dmi("product_name"),
    }


def _read_dmi(field: str) -> str | None:
    try:
        with open(f"/sys/class/dmi/id/{field}", encoding="utf-8") as f:
            value = f.read().strip()
            return value or None
    except OSError:
        return None


def list_services() -> list[dict]:
    """`systemctl list-units --type=service` çıktısını parse eder.
    `systemctl` yoksa (minimal container, systemd olmayan dağıtım) veya
    zaman aşımına uğrarsa boş liste döner — agent ÇÖKMEZ, yalnızca bu
    tek koleksiyon adımı atlanmış olur."""
    try:
        result = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--plain"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("systemctl çalıştırılamadı", exc_info=True)
        return []

    if result.returncode != 0:
        logger.debug("systemctl beklenmeyen çıkış koduyla döndü: %d", result.returncode)

    services: list[dict] = []
    for line in result.stdout.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        unit, load, active, sub = parts[0], parts[1], parts[2], parts[3]
        services.append(
            {
                "name": unit,
                "display_name": None,
                "state": f"{active}/{sub}",
                "startup_type": load,
            }
        )
    return services


def list_sessions() -> list[dict]:
    """`who` çıktısını ayrıştırır. Linux'ta `who` yalnızca O AN
    bağlı oturumları listeler — Windows'un `Disc` (disconnected)
    kavramı yok, bu yüzden `status` her zaman `"active"`. `who`
    yoksa/zaman aşımına uğrarsa boş liste döner, agent ÇÖKMEZ."""
    try:
        result = subprocess.run(["who"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("who çalıştırılamadı", exc_info=True)
        return []

    sessions: list[dict] = []
    for line in result.stdout.splitlines():
        # Format: "alice    pts/0        2026-09-02 08:57 (10.0.213.1)"
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        username, session_name, date, time_of_day = parts[0], parts[1], parts[2], parts[3]
        sessions.append(
            {
                "username": username,
                "session_name": session_name or None,
                "status": "active",
                "logon_time": f"{date} {time_of_day}",
            }
        )
    return sessions
