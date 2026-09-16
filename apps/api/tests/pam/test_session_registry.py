"""Faz 50 — `app/pam/session_registry.py` bellek-içi kayıt defterinin
saf birim testleri (gerçek WebSocket/DB gerektirmez)."""

from uuid import uuid4

import pytest

from app.pam import session_registry

pytestmark = pytest.mark.anyio


async def test_request_termination_returns_false_for_unregistered_session():
    assert session_registry.request_termination(uuid4()) is False


async def test_register_then_request_termination_sets_event():
    session_id = uuid4()
    event = session_registry.register(session_id)
    try:
        assert not event.is_set()
        assert session_registry.is_active(session_id) is True

        assert session_registry.request_termination(session_id) is True
        assert event.is_set()
    finally:
        session_registry.unregister(session_id)


async def test_unregister_makes_session_inactive():
    session_id = uuid4()
    session_registry.register(session_id)
    session_registry.unregister(session_id)

    assert session_registry.is_active(session_id) is False
    assert session_registry.request_termination(session_id) is False


async def test_unregister_is_safe_to_call_twice():
    session_id = uuid4()
    session_registry.register(session_id)
    session_registry.unregister(session_id)
    session_registry.unregister(session_id)  # no-op, must not raise


# ---- Faz 51 — Canlı Oturum İzleme (Shadowing) pub/sub -------------------


async def test_publish_to_shadows_without_subscribers_is_a_noop():
    session_registry.publish_to_shadows(uuid4(), b"4.sync,1.0;")  # must not raise


async def test_subscribe_receives_published_data():
    session_id = uuid4()
    queue = session_registry.subscribe_shadow(session_id)
    try:
        session_registry.publish_to_shadows(session_id, b"4.sync,1.0;")
        item = await queue.get()
        assert item == b"4.sync,1.0;"
    finally:
        session_registry.unsubscribe_shadow(session_id, queue)


async def test_multiple_subscribers_all_receive_the_same_publish():
    session_id = uuid4()
    queue_a = session_registry.subscribe_shadow(session_id)
    queue_b = session_registry.subscribe_shadow(session_id)
    try:
        session_registry.publish_to_shadows(session_id, b"data")
        assert await queue_a.get() == b"data"
        assert await queue_b.get() == b"data"
    finally:
        session_registry.unsubscribe_shadow(session_id, queue_a)
        session_registry.unsubscribe_shadow(session_id, queue_b)


async def test_unregister_sends_none_to_remaining_shadow_subscribers():
    """Bir admin izleme modalını kapatmadan önce birincil oturum
    bitiyorsa (`unregister` çağrılıyorsa), izleyici kuyruğu sonsuza
    kadar BEKLEMEMELİ — `None` göndererek "bağlantıyı kapat" sinyali
    almalı."""
    session_id = uuid4()
    session_registry.register(session_id)
    queue = session_registry.subscribe_shadow(session_id)
    try:
        session_registry.unregister(session_id)
        item = await queue.get()
        assert item is None
    finally:
        session_registry.unsubscribe_shadow(session_id, queue)


async def test_unsubscribe_shadow_is_safe_when_never_subscribed():
    session_registry.unsubscribe_shadow(uuid4(), None)  # type: ignore[arg-type]  # must not raise
