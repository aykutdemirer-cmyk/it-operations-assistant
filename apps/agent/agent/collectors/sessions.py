"""User Sessions Tracking (Faz 34) — platform-özel gerçek implementasyon
`agent/platform/{windows,linux}.py`'de yaşar, bu modül yalnızca ortak
bir giriş noktası + `sessions` listesinden `last_logged_in_user`/
`active_sessions_count` türetme mantığını sağlar (`apps/api/app/agents/
models.py::SessionInfo` ile birebir alan adları: username/session_name/
status/logon_time)."""

from __future__ import annotations

import logging
from datetime import datetime

from agent import platform as agent_platform

logger = logging.getLogger("agent.collectors.sessions")

# `logon_time` platform-bağımsız serbest metin olarak toplanır (bkz.
# platform modülleri) — "en son giriş yapan" kullanıcıyı bulmak için
# BİLİNEN biçimlerle ayrıştırmayı DENERİZ; hiçbiri eşleşmezse uydurma
# bir sıralama YAPMAYIZ, listenin ilk öğesine düşülür (dürüst en-iyi-çaba).
_KNOWN_LOGON_TIME_FORMATS = (
    "%m/%d/%Y %I:%M %p",  # Windows `quser`, en-US yerel ayarı: 9/2/2026 8:57 AM
    "%d.%m.%Y %H:%M",  # Windows `quser`, tr-TR (ve çoğu Avrupa) yerel ayarı: 1.09.2026 16:20
    "%Y-%m-%d %H:%M",  # Linux `who`: 2026-09-02 08:57
)

_ACTIVE_STATUSES = {"active", "disconnected"}


def collect_sessions() -> list[dict]:
    try:
        return agent_platform.resolve().list_sessions()
    except Exception:
        logger.warning("Oturum listesi alınamadı", exc_info=True)
        return []


def _parse_logon_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    for fmt in _KNOWN_LOGON_TIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def summarize_sessions(sessions: list[dict]) -> tuple[str | None, int]:
    """`(last_logged_in_user, active_sessions_count)` döner. Hiç oturum
    yoksa `(None, 0)` — asla uydurulmaz."""
    if not sessions:
        return None, 0

    active_count = sum(1 for s in sessions if (s.get("status") or "").lower() in _ACTIVE_STATUSES)

    parsed = [(s, _parse_logon_time(s.get("logon_time"))) for s in sessions]
    with_time = [(s, t) for s, t in parsed if t is not None]
    if with_time:
        last_user = max(with_time, key=lambda pair: pair[1])[0].get("username")
    else:
        last_user = sessions[0].get("username")
    return last_user, active_count
