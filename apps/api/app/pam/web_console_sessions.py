"""Faz 76 — PAM Web Konsolu oturumları için bellek-içi kayıt defteri.
RDP/SSH'ın `session_registry.py`'sinden BİLİNÇLİ olarak AYRI ve daha
basit: o modül canlı, kalıcı bir WebSocket/TCP bağlantısının "kill"
olayını yönetiyor; burada her istek BAĞIMSIZ (kalıcı bir soket YOK) —
yalnızca "bu opak session_id hâlâ geçerli mi ve hangi hedefe/hangi
çerezlerle gidiyor" sorusuna cevap veren, TTL'li bir sözlük yeterli.

`session_id` (bir UUID, `pam_session_logs.id`) burada RDP/SSH'ın JWT-
query-string ödünleşimiyle AYNI rolü oynuyor — tarayıcının `<iframe
src>`'i özel bir `Authorization` header'ı TAŞIYAMADIĞI için, gerçek
yetkilendirme YALNIZCA oturum KURULURKEN (`POST .../session`, normal
`Authorization: Bearer` ile) yapılır; sonraki her proxy isteği bu
tahmin edilemez (kriptografik UUID) kapasiteyi kanıtlar."""

from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import UUID

from app.pam.web_console import WebConsoleTarget


@dataclass
class WebConsoleSession:
    session_id: UUID
    user_id: UUID
    target: WebConsoleTarget
    cookies: dict[str, str]
    expires_at: float


_sessions: dict[UUID, WebConsoleSession] = {}


def register(
    session_id: UUID, *, user_id: UUID, target: WebConsoleTarget, cookies: dict[str, str], ttl_seconds: int
) -> WebConsoleSession:
    session = WebConsoleSession(
        session_id=session_id, user_id=user_id, target=target, cookies=cookies, expires_at=time.time() + ttl_seconds
    )
    _sessions[session_id] = session
    return session


def get(session_id: UUID) -> WebConsoleSession | None:
    session = _sessions.get(session_id)
    if session is None:
        return None
    if time.time() > session.expires_at:
        _sessions.pop(session_id, None)
        return None
    return session


def unregister(session_id: UUID) -> None:
    _sessions.pop(session_id, None)
