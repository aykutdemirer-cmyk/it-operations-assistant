"""`app/snmp/poller.py` (Faz 23 — SNMP Polling Engine) için testler.
Gerçek ağ/cihaz yok — `SNMPClient.poll_asset` mock'lanır."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.snmp.models import SNMPPollResult
from app.snmp.poller import PollingEngine, _max_concurrency_from_env

pytestmark = pytest.mark.anyio


def _asset(asset_id=None, ip="10.0.9.10") -> dict:
    return {"id": asset_id or uuid4(), "ip_address": ip}


def _success_result(asset_id) -> SNMPPollResult:
    return SNMPPollResult(
        asset_id=asset_id, polled_at=datetime.now(timezone.utc), status="success"
    )


class _FakeClient:
    """`SNMPClient` yerine geçen, gerçek ağ kullanmayan sahte client."""

    def __init__(self, side_effect=None):
        self.calls: list = []
        self._side_effect = side_effect

    async def poll_asset(self, profile, host, asset_id):
        self.calls.append(asset_id)
        if self._side_effect is not None:
            return await self._side_effect(profile, host, asset_id)
        return _success_result(asset_id)


# 1. Profil olmayan asset'ler için not_configured (gerçek poll hiç çağrılmaz)
async def test_poll_all_returns_not_configured_for_assets_without_profile(monkeypatch):
    monkeypatch.delenv("SNMP_TARGET_ASSET_ID", raising=False)
    assets = [_asset(), _asset(), _asset()]
    client = _FakeClient()
    engine = PollingEngine(client=client)

    batch = await engine.poll_all(assets)

    assert batch.total == 3
    assert batch.polled == 0
    assert batch.not_configured == 3
    assert all(r.status == "not_configured" for r in batch.results)
    assert client.calls == []


# 2. Yalnızca profili çözülen asset gerçekten poll edilir
async def test_poll_all_polls_only_assets_with_resolved_profile(monkeypatch):
    target = _asset()
    other = _asset()
    monkeypatch.setenv("SNMP_TARGET_ASSET_ID", str(target["id"]))
    monkeypatch.setenv("SNMP_TARGET_COMMUNITY_REF", "SNMP_V2C_COMMUNITY")

    client = _FakeClient()
    engine = PollingEngine(client=client)

    batch = await engine.poll_all([target, other])

    assert batch.total == 2
    assert batch.polled == 1
    assert batch.not_configured == 1
    assert client.calls == [target["id"]]
    by_id = {r.asset_id: r for r in batch.results}
    assert by_id[target["id"]].status == "success"
    assert by_id[other["id"]].status == "not_configured"


# 3. Eşzamanlılık limiti aşılmıyor
async def test_concurrency_limit_is_respected(monkeypatch):
    # Her asset için ayrı ayrı env eşleşmesi mümkün olmadığından, engine'i
    # doğrudan bir _FakeClient ile ve `conn`suz çağırıp (env fallback yolu)
    # `profile_store.get_profile_for_asset`'i monkeypatch'leyerek her
    # asset'e sahte bir profil döndürecek şekilde test ediyoruz.
    assets = [_asset() for _ in range(6)]

    fake_profile = object()
    monkeypatch.setattr("app.snmp.profile_store.get_profile_for_asset", lambda asset_id: fake_profile)

    in_flight = 0
    max_in_flight = 0
    lock = asyncio.Lock()

    async def _slow_side_effect(profile, host, asset_id):
        nonlocal in_flight, max_in_flight
        async with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.02)
        async with lock:
            in_flight -= 1
        return _success_result(asset_id)

    client = _FakeClient(side_effect=_slow_side_effect)
    engine = PollingEngine(max_concurrency=2, client=client)

    batch = await engine.poll_all(assets)

    assert batch.polled == 6
    assert max_in_flight <= 2


# 4. Bir cihazın hatası diğerlerini durdurmaz; ham exception sızdırılmaz
async def test_one_device_failure_does_not_stop_others(monkeypatch):
    fake_profile = object()
    monkeypatch.setattr("app.snmp.profile_store.get_profile_for_asset", lambda asset_id: fake_profile)

    good = _asset()
    bad = _asset()

    async def _side_effect(profile, host, asset_id):
        if asset_id == bad["id"]:
            raise RuntimeError("gizli-detay-sizdirilmamali: bağlantı çöktü")
        return _success_result(asset_id)

    client = _FakeClient(side_effect=_side_effect)
    engine = PollingEngine(client=client)

    batch = await engine.poll_all([good, bad])

    by_id = {r.asset_id: r for r in batch.results}
    assert by_id[good["id"]].status == "success"
    assert by_id[bad["id"]].status == "unreachable"
    assert "gizli-detay-sizdirilmamali" not in (by_id[bad["id"]].error or "")


# 5. asyncio.CancelledError yutulmuyor — dış iptal düzgün yayılıyor
async def test_cancellation_propagates(monkeypatch):
    fake_profile = object()
    monkeypatch.setattr("app.snmp.profile_store.get_profile_for_asset", lambda asset_id: fake_profile)

    async def _hang_forever(profile, host, asset_id):
        await asyncio.sleep(10)
        return _success_result(asset_id)

    client = _FakeClient(side_effect=_hang_forever)
    engine = PollingEngine(client=client)

    task = asyncio.ensure_future(engine.poll_all([_asset()]))
    await asyncio.sleep(0.01)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


# 6. SNMP_MAX_CONCURRENCY env değişkeni okunuyor
def test_max_concurrency_reads_env_var(monkeypatch):
    monkeypatch.setenv("SNMP_MAX_CONCURRENCY", "12")
    assert _max_concurrency_from_env() == 12


# 7. Env yoksa güvenli, düşük bir varsayılan kullanılıyor
def test_max_concurrency_default_is_low_and_safe(monkeypatch):
    monkeypatch.delenv("SNMP_MAX_CONCURRENCY", raising=False)
    value = _max_concurrency_from_env()
    assert 1 <= value <= 10


# 8. Geçersiz/negatif env değeri varsayılana düşüyor
def test_max_concurrency_invalid_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("SNMP_MAX_CONCURRENCY", "not-a-number")
    default = _max_concurrency_from_env()
    monkeypatch.setenv("SNMP_MAX_CONCURRENCY", "-3")
    assert _max_concurrency_from_env() == default
    monkeypatch.setenv("SNMP_MAX_CONCURRENCY", "0")
    assert _max_concurrency_from_env() == default


# 9. Boş asset listesi hatasız, boş bir batch sonucu döner
async def test_poll_all_with_empty_asset_list():
    engine = PollingEngine(client=_FakeClient())
    batch = await engine.poll_all([])

    assert batch.total == 0
    assert batch.polled == 0
    assert batch.not_configured == 0
    assert batch.results == []


# 10. PollBatchResult sayıları gerçek karışık sonuçları doğru yansıtıyor
async def test_batch_result_counts_are_accurate(monkeypatch):
    target = _asset()
    others = [_asset(), _asset()]
    monkeypatch.setenv("SNMP_TARGET_ASSET_ID", str(target["id"]))
    monkeypatch.setenv("SNMP_TARGET_COMMUNITY_REF", "SNMP_V2C_COMMUNITY")

    engine = PollingEngine(client=_FakeClient())
    batch = await engine.poll_all([target, *others])

    assert batch.total == 3
    assert batch.polled == 1
    assert batch.not_configured == 2
    assert batch.completed_at >= batch.started_at
    assert batch.duration_ms >= 0
