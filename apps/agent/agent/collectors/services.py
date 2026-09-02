"""Windows Services / Linux systemd services — platform-özel gerçek
implementasyon `agent/platform/{windows,linux}.py`'de yaşar, bu modül
yalnızca ortak bir giriş noktası sağlar (`apps/api/app/agents/models.py
::ServiceInfo` ile birebir alan adları: name/display_name/state/
startup_type)."""

from __future__ import annotations

import logging

from agent import platform as agent_platform

logger = logging.getLogger("agent.collectors.services")


def collect_services() -> list[dict]:
    try:
        return agent_platform.resolve().list_services()
    except Exception:
        logger.warning("Servis listesi alınamadı", exc_info=True)
        return []
