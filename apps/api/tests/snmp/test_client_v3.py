"""`app/snmp/client.py`'nin SNMPv3 yolu için gerçek ağ/cihaz
gerektirmeyen testler (Faz 22.4).

`app.snmp.client.v3_get_cmd`/`v3_bulk_cmd` mock'lanır — hiçbir gerçek
SNMP paketi gönderilmez. `UsmUserData` gerçek nesnesi mock'lanmaz;
`_build_usm_user_data`'nın auth/priv protokolünü asla pysnmp'nin kendi
(MD5/DES) varsayılanına bırakmadığını doğrudan bu gerçek nesne üzerinden
doğruluyoruz."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pyasn1.type.univ import OctetString
from pysnmp.hlapi.v3arch.asyncio import (
    usmAesCfb128Protocol,
    usmAesCfb256Protocol,
    usmDESPrivProtocol,
    usmHMAC192SHA256AuthProtocol,
    usmHMACMD5AuthProtocol,
    usmHMACSHAAuthProtocol,
)
from pysnmp.proto import errind
from pysnmp.smi import builder, view
from pysnmp.smi.rfc1902 import ObjectIdentity, ObjectType

from app.snmp.client import SNMPClient
from app.snmp.credentials import SNMPProfile
from app.snmp.oid_map import SYSTEM_OIDS

pytestmark = pytest.mark.anyio

_MIB_VIEW = view.MibViewController(builder.MibBuilder())
_AUTH_SECRET_ENV = "TEST_SNMP_V3_AUTH_SECRET"
_AUTH_SECRET_VALUE = "cok-gizli-auth-parolasi-asla-gorunmemeli"
_PRIV_SECRET_ENV = "TEST_SNMP_V3_PRIV_SECRET"
_PRIV_SECRET_VALUE = "cok-gizli-priv-parolasi-asla-gorunmemeli"


def _vb(oid: str, value) -> ObjectType:
    ot = ObjectType(ObjectIdentity(oid), value)
    ot.resolve_with_mib(_MIB_VIEW)
    return ot


def _system_response():
    var_binds = tuple(
        _vb(oid, OctetString(f"value-{name}")) for name, oid in SYSTEM_OIDS.items()
    )
    return (None, 0, 0, var_binds)


def _v3_profile(**overrides) -> SNMPProfile:
    defaults = dict(asset_id=uuid4(), version="v3", port=161, timeout_seconds=1.0, retries=1)
    defaults.update(overrides)
    return SNMPProfile(**defaults)


@pytest.fixture(autouse=True)
def _v3_env(monkeypatch):
    monkeypatch.setenv(_AUTH_SECRET_ENV, _AUTH_SECRET_VALUE)
    monkeypatch.setenv(_PRIV_SECRET_ENV, _PRIV_SECRET_VALUE)


def _no_interfaces_bulk():
    return AsyncMock(return_value=(None, 0, 0, ()))


# 1. noAuthNoPriv — başarılı GET
async def test_v3_noauthnopriv_successful_get():
    profile = _v3_profile(username="readonly")
    with (
        patch("app.snmp.client.v3_get_cmd", new=AsyncMock(return_value=_system_response())),
        patch("app.snmp.client.v3_bulk_cmd", new=_no_interfaces_bulk()),
    ):
        result = await SNMPClient().poll_asset(profile, "10.0.9.1", profile.asset_id)

    assert result.status == "success"
    assert result.system is not None


# 2. authNoPriv — başarılı GET, gerçek UsmUserData security_level doğru
async def test_v3_authnopriv_successful_get():
    profile = _v3_profile(
        username="monitoring", auth_protocol="SHA", auth_credential_ref=_AUTH_SECRET_ENV
    )
    get_mock = AsyncMock(return_value=_system_response())
    with patch("app.snmp.client.v3_get_cmd", new=get_mock), patch(
        "app.snmp.client.v3_bulk_cmd", new=_no_interfaces_bulk()
    ):
        result = await SNMPClient().poll_asset(profile, "10.0.9.1", profile.asset_id)

    assert result.status == "success"
    usm_user_data = get_mock.call_args_list[0].args[1]
    assert usm_user_data.security_level == "authNoPriv"
    assert usm_user_data.authentication_protocol == usmHMACSHAAuthProtocol


# 3. authPriv — başarılı GET, security_level authPriv
async def test_v3_authpriv_successful_get():
    profile = _v3_profile(
        username="monitoring",
        auth_protocol="SHA",
        auth_credential_ref=_AUTH_SECRET_ENV,
        priv_protocol="AES",
        priv_credential_ref=_PRIV_SECRET_ENV,
    )
    get_mock = AsyncMock(return_value=_system_response())
    with patch("app.snmp.client.v3_get_cmd", new=get_mock), patch(
        "app.snmp.client.v3_bulk_cmd", new=_no_interfaces_bulk()
    ):
        result = await SNMPClient().poll_asset(profile, "10.0.9.1", profile.asset_id)

    assert result.status == "success"
    usm_user_data = get_mock.call_args_list[0].args[1]
    assert usm_user_data.security_level == "authPriv"
    assert usm_user_data.privacy_protocol == usmAesCfb128Protocol


# 4. Auth protokolü ASLA pysnmp'nin MD5 varsayılanına düşmüyor
def test_v3_auth_protocol_never_silently_defaults_to_md5():
    usm_user_data = SNMPClient._build_usm_user_data(
        "monitoring", _AUTH_SECRET_VALUE, "SHA256", None, None
    )
    assert usm_user_data.authentication_protocol == usmHMAC192SHA256AuthProtocol
    assert usm_user_data.authentication_protocol != usmHMACMD5AuthProtocol


# 5. Priv protokolü ASLA pysnmp'nin DES varsayılanına düşmüyor
def test_v3_priv_protocol_never_silently_defaults_to_des():
    usm_user_data = SNMPClient._build_usm_user_data(
        "monitoring", _AUTH_SECRET_VALUE, "SHA", _PRIV_SECRET_VALUE, "AES256"
    )
    assert usm_user_data.privacy_protocol == usmAesCfb256Protocol
    assert usm_user_data.privacy_protocol != usmDESPrivProtocol


# 6. auth_credential_ref .env'de çözülemezse not_configured
async def test_v3_not_configured_when_auth_secret_missing(monkeypatch):
    monkeypatch.delenv(_AUTH_SECRET_ENV, raising=False)
    profile = _v3_profile(
        username="monitoring", auth_protocol="SHA", auth_credential_ref=_AUTH_SECRET_ENV
    )
    get_mock = AsyncMock()
    with patch("app.snmp.client.v3_get_cmd", new=get_mock):
        result = await SNMPClient().poll_asset(profile, "10.0.9.1", profile.asset_id)

    assert result.status == "not_configured"
    get_mock.assert_not_called()


# 7. priv_credential_ref .env'de çözülemezse not_configured
async def test_v3_not_configured_when_priv_secret_missing(monkeypatch):
    monkeypatch.delenv(_PRIV_SECRET_ENV, raising=False)
    profile = _v3_profile(
        username="monitoring",
        auth_protocol="SHA",
        auth_credential_ref=_AUTH_SECRET_ENV,
        priv_protocol="AES",
        priv_credential_ref=_PRIV_SECRET_ENV,
    )
    get_mock = AsyncMock()
    with patch("app.snmp.client.v3_get_cmd", new=get_mock):
        result = await SNMPClient().poll_asset(profile, "10.0.9.1", profile.asset_id)

    assert result.status == "not_configured"
    get_mock.assert_not_called()


# 8. Timeout
async def test_v3_timeout():
    profile = _v3_profile(username="readonly")
    with patch(
        "app.snmp.client.v3_get_cmd", new=AsyncMock(return_value=(errind.requestTimedOut, 0, 0, ()))
    ):
        result = await SNMPClient().poll_asset(profile, "10.0.9.1", profile.asset_id)

    assert result.status == "timeout"


# 9. USM kimlik doğrulama reddi (yanlış kullanıcı/parola) -> authentication_failed
async def test_v3_authentication_failure():
    profile = _v3_profile(
        username="monitoring", auth_protocol="SHA", auth_credential_ref=_AUTH_SECRET_ENV
    )
    with patch(
        "app.snmp.client.v3_get_cmd",
        new=AsyncMock(return_value=(errind.unknownUserName, 0, 0, ())),
    ):
        result = await SNMPClient().poll_asset(profile, "10.0.9.1", profile.asset_id)

    assert result.status == "authentication_failed"


# 10. Yanlış priv key (decryption error) -> authentication_failed
async def test_v3_decryption_error_maps_to_authentication_failed():
    profile = _v3_profile(
        username="monitoring",
        auth_protocol="SHA",
        auth_credential_ref=_AUTH_SECRET_ENV,
        priv_protocol="AES",
        priv_credential_ref=_PRIV_SECRET_ENV,
    )
    with patch(
        "app.snmp.client.v3_get_cmd",
        new=AsyncMock(return_value=(errind.decryptionError, 0, 0, ())),
    ):
        result = await SNMPClient().poll_asset(profile, "10.0.9.1", profile.asset_id)

    assert result.status == "authentication_failed"


# 11. Ortak parsing/orkestrasyon kodu v3'te de aynı şekilde çalışıyor
async def test_v3_reuses_shared_system_and_interface_parsing():
    profile = _v3_profile(username="readonly")
    with (
        patch("app.snmp.client.v3_get_cmd", new=AsyncMock(return_value=_system_response())),
        patch("app.snmp.client.v3_bulk_cmd", new=_no_interfaces_bulk()),
    ):
        result = await SNMPClient().poll_asset(profile, "10.0.9.1", profile.asset_id)

    assert result.system.sys_name is not None
    assert result.interfaces == []


# 12. Secret hiçbir log kaydında görünmez (auth+priv)
async def test_v3_secret_never_appears_in_logs(caplog):
    profile = _v3_profile(
        username="monitoring",
        auth_protocol="SHA",
        auth_credential_ref=_AUTH_SECRET_ENV,
        priv_protocol="AES",
        priv_credential_ref=_PRIV_SECRET_ENV,
    )
    with (
        caplog.at_level(logging.DEBUG),
        patch("app.snmp.client.v3_get_cmd", new=AsyncMock(return_value=(errind.unknownUserName, 0, 0, ()))),
    ):
        await SNMPClient().poll_asset(profile, "10.0.9.1", profile.asset_id)

    for record in caplog.records:
        message = record.getMessage()
        assert _AUTH_SECRET_VALUE not in message
        assert _PRIV_SECRET_VALUE not in message


# 13. Secret hiçbir API response'unda (model serileştirmesinde) görünmez
async def test_v3_secret_never_appears_in_response_serialization():
    profile = _v3_profile(
        username="monitoring",
        auth_protocol="SHA",
        auth_credential_ref=_AUTH_SECRET_ENV,
        priv_protocol="AES",
        priv_credential_ref=_PRIV_SECRET_ENV,
    )
    with patch(
        "app.snmp.client.v3_get_cmd", new=AsyncMock(return_value=(errind.requestTimedOut, 0, 0, ()))
    ):
        result = await SNMPClient().poll_asset(profile, "10.0.9.1", profile.asset_id)

    serialized = result.model_dump_json()
    assert _AUTH_SECRET_VALUE not in serialized
    assert _PRIV_SECRET_VALUE not in serialized


# 14. SnmpEngine her poll sonunda kapatılıyor (kaynak sızıntısı yok)
async def test_v3_engine_closed_after_poll():
    profile = _v3_profile(username="readonly")
    fake_engine = MagicMock()
    fake_engine.close_dispatcher = MagicMock()
    with (
        patch("app.snmp.client.SnmpEngine", return_value=fake_engine),
        patch("app.snmp.client.v3_get_cmd", new=AsyncMock(return_value=_system_response())),
        patch("app.snmp.client.v3_bulk_cmd", new=_no_interfaces_bulk()),
    ):
        await SNMPClient().poll_asset(profile, "10.0.9.1", profile.asset_id)

    fake_engine.close_dispatcher.assert_called_once()


# 15. Engine, hata durumunda da kapatılıyor
async def test_v3_engine_closed_even_on_error():
    profile = _v3_profile(username="readonly")
    fake_engine = MagicMock()
    fake_engine.close_dispatcher = MagicMock()
    with (
        patch("app.snmp.client.SnmpEngine", return_value=fake_engine),
        patch("app.snmp.client.v3_get_cmd", new=AsyncMock(return_value=(errind.requestTimedOut, 0, 0, ()))),
    ):
        await SNMPClient().poll_asset(profile, "10.0.9.1", profile.asset_id)

    fake_engine.close_dispatcher.assert_called_once()
