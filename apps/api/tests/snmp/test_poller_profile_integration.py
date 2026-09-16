"""`PollingEngine`'in gerçek `asset_snmp_profiles` DB ilişkisiyle
entegrasyonu için testler (Faz 29.5). Gerçek SNMP ağ trafiği yok —
`SNMPClient.poll_asset` mock'lanır. `isolated_db` sayesinde gerçek/kalıcı
veriye hiçbir etkisi yok (bkz. kök `conftest.py`)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.db.asset_snmp_profiles import assign_profile_to_asset
from app.db.assets import upsert_asset
from app.db.snmp_profiles import insert_profile
from app.snmp.models import SNMPPollResult
from app.snmp.poller import PollingEngine

pytestmark = pytest.mark.anyio


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _seed_asset(conn, **overrides) -> dict:
    defaults = dict(
        ip_address="10.0.213.5",
        hostname="switch01",
        mac_address=None,
        vendor=None,
        device_type="switch",
        confidence="medium",
        status="up",
        open_ports=[],
        evidence=[],
        last_seen=_now(),
    )
    defaults.update(overrides)
    return await upsert_asset(conn, **defaults)


async def _seed_profile(conn, **overrides) -> dict:
    defaults = dict(
        name="Core Switch SNMP",
        target_host="",
        port=161,
        version="v2c",
        timeout_seconds=2.0,
        retries=2,
        enabled=True,
        community_ref="SNMP_CORE_COMMUNITY",
        username=None,
        auth_protocol=None,
        auth_credential_ref=None,
        priv_protocol=None,
        priv_credential_ref=None,
    )
    defaults.update(overrides)
    return await insert_profile(conn, **defaults)


def _success_result(asset_id) -> SNMPPollResult:
    return SNMPPollResult(asset_id=asset_id, polled_at=_now(), status="success")


async def test_poll_all_uses_db_assigned_profile(isolated_db, monkeypatch):
    monkeypatch.delenv("SNMP_TARGET_ASSET_ID", raising=False)
    asset = await _seed_asset(isolated_db)
    profile = await _seed_profile(isolated_db)
    await assign_profile_to_asset(isolated_db, asset_id=asset["id"], profile_id=profile["id"])

    with patch(
        "app.snmp.client.SNMPClient.poll_asset",
        AsyncMock(return_value=_success_result(asset["id"])),
    ) as mock_poll:
        batch = await PollingEngine().poll_all([asset], isolated_db)

    assert batch.polled == 1
    assert batch.results[0].status == "success"
    mock_poll.assert_called_once()
    # Poll her zaman asset'in GERÇEK IP'sine gider — profile.target_host
    # (burada boş) hiç kullanılmaz. `called_host` bir DÜZ STRING olmalı
    # — `assets.ip_address` (INET) asyncpg'den bir `ipaddress.
    # IPv4Address` NESNESİ olarak gelir (bkz. `poller.py::_poll_one`'daki
    # `str(...)` düzeltmesinin gerekçesi — gerçek kullanıcı bildirimiyle
    # bulunan bir hata: bu dönüşüm OLMADAN pysnmp'nin `slim.get()`'i
    # `TypeError: argument of type 'IPv4Address' is not a container or
    # iterable` ile çöküyordu, DB'den gelen HİÇBİR asset asla gerçekten
    # poll edilemiyordu). Bu assertion BİLE ÖNCEDEN yanlışlıkla
    # geçiyordu — `called_host` de dönüştürülmemiş bir `IPv4Address`
    # olduğu için `==` iki eşit nesneyi karşılaştırıp True dönüyordu;
    # gerçek TİP hiç kontrol edilmiyordu.
    called_profile, called_host, called_asset_id = mock_poll.call_args.args
    assert called_host == str(asset["ip_address"])
    assert isinstance(called_host, str)
    assert called_asset_id == asset["id"]


async def test_poll_all_returns_not_configured_when_no_assignment(isolated_db, monkeypatch):
    monkeypatch.delenv("SNMP_TARGET_ASSET_ID", raising=False)
    asset = await _seed_asset(isolated_db)

    batch = await PollingEngine().poll_all([asset], isolated_db)

    assert batch.not_configured == 1
    assert batch.results[0].status == "not_configured"


async def test_poll_all_returns_not_configured_when_assigned_profile_is_disabled(
    isolated_db, monkeypatch
):
    monkeypatch.delenv("SNMP_TARGET_ASSET_ID", raising=False)
    asset = await _seed_asset(isolated_db)
    profile = await _seed_profile(isolated_db, enabled=False)
    await assign_profile_to_asset(isolated_db, asset_id=asset["id"], profile_id=profile["id"])

    with patch("app.snmp.client.SNMPClient.poll_asset", AsyncMock()) as mock_poll:
        batch = await PollingEngine().poll_all([asset], isolated_db)

    assert batch.results[0].status == "not_configured"
    mock_poll.assert_not_called()


async def test_poll_all_ignores_deleted_asset_gracefully(isolated_db, monkeypatch):
    """Asset listesi çağıran taraftan (route) geldiği için DB'de artık
    olmayan bir asset teorik olarak batch'e girmez, ama `_poll_one`'a
    hâlâ elle bir dict verilirse (savunma amaçlı) DB ataması bulunamaz
    ve dürüstçe `not_configured` döner — hiçbir exception dışarı sızmaz."""
    monkeypatch.delenv("SNMP_TARGET_ASSET_ID", raising=False)
    phantom_asset = {"id": uuid4(), "ip_address": "10.0.213.99"}

    batch = await PollingEngine().poll_all([phantom_asset], isolated_db)

    assert batch.results[0].status == "not_configured"


async def test_poll_all_falls_back_to_env_target_when_no_db_assignment(isolated_db, monkeypatch):
    """DB'de bir atama yoksa geriye dönük uyumluluk için `.env` tabanlı
    tek-hedef fallback hâlâ çalışır (bilinçli olarak kaldırılmadı)."""
    asset = await _seed_asset(isolated_db)
    monkeypatch.setenv("SNMP_TARGET_ASSET_ID", str(asset["id"]))
    monkeypatch.setenv("SNMP_TARGET_COMMUNITY_REF", "SNMP_V2C_COMMUNITY")

    with patch(
        "app.snmp.client.SNMPClient.poll_asset",
        AsyncMock(return_value=_success_result(asset["id"])),
    ) as mock_poll:
        batch = await PollingEngine().poll_all([asset], isolated_db)

    assert batch.polled == 1
    mock_poll.assert_called_once()


async def test_poll_all_prefers_db_assignment_over_env_fallback(isolated_db, monkeypatch):
    """Hem DB ataması hem `.env` fallback'i aynı anda çözülebilir
    durumdaysa DB ataması ÖNCELİKLİDİR (env asla sessizce üzerine
    yazmaz)."""
    asset = await _seed_asset(isolated_db)
    db_profile = await _seed_profile(isolated_db, name="DB Profile", community_ref="SNMP_DB_COMMUNITY")
    await assign_profile_to_asset(isolated_db, asset_id=asset["id"], profile_id=db_profile["id"])

    monkeypatch.setenv("SNMP_TARGET_ASSET_ID", str(asset["id"]))
    monkeypatch.setenv("SNMP_TARGET_COMMUNITY_REF", "SNMP_ENV_COMMUNITY")

    with patch(
        "app.snmp.client.SNMPClient.poll_asset",
        AsyncMock(return_value=_success_result(asset["id"])),
    ) as mock_poll:
        await PollingEngine().poll_all([asset], isolated_db)

    used_profile = mock_poll.call_args.args[0]
    assert used_profile.community_ref == "SNMP_DB_COMMUNITY"
