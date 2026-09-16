"""Faz 50 — canlı PAM oturumlarının bellek-içi kayıt defteri. Admin'in
"Oturumu Anında Kapat" isteğini, o oturumu ANLIK olarak köprüleyen
WebSocket handler'ına (aynı süreç içinde çalışan bir `asyncio.Task`)
iletmenin tek yolu bu — DB'ye bir "kapat" bayrağı YAZMAK yeterli
DEĞİLDİR, çünkü handler zaten `websocket.receive_*()`/guacd okuma
döngüsünde ASILI bekliyor, periyodik olarak DB'yi POLLAMIYOR.

**Kasıtlı mimari sınır:** bu registry tek bir Python SÜRECİ içinde
paylaşılan bir `dict` — bu proje HİÇBİR ZAMAN `uvicorn --workers N`
(çoklu süreç) İLE ÇALIŞTIRILMADI (bkz. `.claude/launch.json`/production
başlatma komutu, hep tek süreç). Çoklu-worker bir dağıtıma geçilirse bu
registry Redis gibi paylaşımlı bir mekanizmaya taşınmalı — bugün için
gereksiz bir soyutlama olurdu."""

from __future__ import annotations

import asyncio
from uuid import UUID

_active_sessions: dict[UUID, asyncio.Event] = {}

# Faz 51 — Canlı Oturum İzleme (Shadowing). Bir RDP oturumunun guacd→
# tarayıcı yönündeki HER tam Guacamole instruction grubu (bkz. `app/pam/
# guacd.py::_pump_guacd_to_websocket`), o oturuma abone olmuş HER "izleme"
# WebSocket'ine de (salt-okunur, girdi göndermez) aynen iletilir. Bir
# oturumun aboneliği yoksa (`_shadow_queues.get(session_id)` boş/None)
# yayın hiçbir maliyet getirmez — normal akışa dokunmaz.
_shadow_queues: dict[UUID, set["asyncio.Queue[bytes]"]] = {}


def register(session_id: UUID) -> asyncio.Event:
    event = asyncio.Event()
    _active_sessions[session_id] = event
    return event


def unregister(session_id: UUID) -> None:
    _active_sessions.pop(session_id, None)
    # Hâlâ dinleyen izleyiciler varsa (admin izleme modalını kapatmadan
    # önce oturum bittiyse) onlara `None` göndererek "oturum bitti,
    # bağlantıyı kapat" sinyali veriyoruz — sonsuza kadar boş bir kuyruğu
    # BEKLEMEK yerine.
    for queue in _shadow_queues.pop(session_id, ()):
        queue.put_nowait(None)


def subscribe_shadow(session_id: UUID) -> "asyncio.Queue[bytes | None]":
    """Faz 51 — "Canlı İzle" WebSocket'i bu kuyruğu okuyarak birincil
    oturumun guacd çıktısını ANLIK olarak alır. `None` gelmesi oturumun
    bittiği/registry'den kaldırıldığı anlamına gelir — çağıran taraf
    bunu bağlantıyı kapatma sinyali olarak yorumlamalı."""
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    _shadow_queues.setdefault(session_id, set()).add(queue)
    return queue


def unsubscribe_shadow(session_id: UUID, queue: "asyncio.Queue[bytes | None]") -> None:
    subscribers = _shadow_queues.get(session_id)
    if subscribers is not None:
        subscribers.discard(queue)
        if not subscribers:
            _shadow_queues.pop(session_id, None)


def publish_to_shadows(session_id: UUID, data: bytes) -> None:
    for queue in _shadow_queues.get(session_id, ()):
        queue.put_nowait(data)


def request_termination(session_id: UUID) -> bool:
    """Admin'in "Oturumu Kapat" eylemi — oturum bu SÜREÇTE aktifse
    (registry'de bulunuyorsa) kill event'i tetikler ve `True` döner.
    Bulunamazsa (oturum zaten bitmiş, ya da backend bu oturum
    başladıktan SONRA yeniden başlatılmış) `False` döner — çağıran
    taraf bunu 409'a çevirir."""
    event = _active_sessions.get(session_id)
    if event is None:
        return False
    event.set()
    return True


def is_active(session_id: UUID) -> bool:
    return session_id in _active_sessions
