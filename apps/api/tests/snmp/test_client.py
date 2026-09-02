"""`app/snmp/client.py` için gerçek ağ/cihaz gerektirmeyen testler.

Hiçbir gerçek SNMP paketı gönderilmez — `pysnmp.hlapi.v1arch.asyncio.
slim.Slim.get`/`.bulk` metotları mock'lanır (bkz. Faz 22.2: "mock SNMP
transport, gerçek cihaz gerekmez"). Yanıtlar gerçek pysnmp/pyasn1
tipleriyle (`OctetString`, `TimeTicks`, `Counter32`, `Counter64`, ...)
kurulur ki parsing kodu gerçek bir yanıtla aynı şekilde test edilsin."""

import logging
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pyasn1.type.univ import ObjectIdentifier, OctetString
from pysnmp.proto import errind
from pysnmp.proto.rfc1902 import Counter32, Counter64, Integer32, TimeTicks
from pysnmp.smi import builder, view
from pysnmp.smi.rfc1902 import ObjectIdentity, ObjectType

from app.snmp.client import SNMPClient, _LAST_SAMPLES
from app.snmp.credentials import SNMPProfile
from app.snmp.oid_map import INTERFACE_OIDS, SYSTEM_OIDS

pytestmark = pytest.mark.anyio

_MIB_VIEW = view.MibViewController(builder.MibBuilder())
_SECRET_ENV_VAR = "TEST_SNMP_CLIENT_COMMUNITY"
_SECRET_VALUE = "cok-gizli-topluluk-dizesi-asla-gorunmemeli"


def _vb(oid: str, value) -> ObjectType:
    ot = ObjectType(ObjectIdentity(oid), value)
    ot.resolve_with_mib(_MIB_VIEW)
    return ot


def _profile(**overrides) -> SNMPProfile:
    defaults = dict(
        asset_id=uuid4(),
        version="v2c",
        port=161,
        timeout_seconds=1.0,
        retries=1,
        community_ref=_SECRET_ENV_VAR,
    )
    defaults.update(overrides)
    return SNMPProfile(**defaults)


def _system_response(**overrides):
    values = {
        "sysDescr": OctetString("Cisco IOS Switch"),
        "sysObjectID": ObjectIdentifier("1.3.6.1.4.1.9.1.1"),
        "sysUpTime": TimeTicks(123456),
        "sysName": OctetString("core-sw-01"),
    }
    values.update(overrides)
    var_binds = tuple(_vb(SYSTEM_OIDS[name], values[name]) for name in SYSTEM_OIDS)
    return (None, 0, 0, var_binds)


_EXT_IF_COLUMNS = ("ifName", "ifHCInOctets", "ifHCOutOctets")


def _interface_response(if_index: int = 1, **overrides) -> tuple:
    """`client.py`'nin bir interface için gönderdiği İKİ ayrı GET'e
    (`ifTable` core + `ifXTable` ext — bkz. ifXTable fallback düzeltmesi)
    karşılık gelen bir yanıt ÇİFTİ döner. Çağıran taraf `_sequential_get`
    içine `*_interface_response(...)` ile AÇARAK geçirmeli (iki ardışık
    yanıt olarak)."""
    values = {
        "ifDescr": OctetString("GigabitEthernet0/1"),
        "ifAdminStatus": Integer32(1),
        "ifOperStatus": Integer32(1),
        "ifSpeed": Counter32(1_000_000_000),
        "ifInOctets": Counter32(1_000),
        "ifOutOctets": Counter32(2_000),
        "ifName": OctetString("Gi0/1"),
        "ifHCInOctets": Counter64(100_000),
        "ifHCOutOctets": Counter64(200_000),
        "ifInErrors": Counter32(0),
        "ifOutErrors": Counter32(0),
    }
    values.update(overrides)
    core_names = [name for name in INTERFACE_OIDS if name not in _EXT_IF_COLUMNS]
    core_var_binds = tuple(_vb(f"{INTERFACE_OIDS[name]}.{if_index}", values[name]) for name in core_names)
    ext_var_binds = tuple(_vb(f"{INTERFACE_OIDS[name]}.{if_index}", values[name]) for name in _EXT_IF_COLUMNS)
    return (None, 0, 0, core_var_binds), (None, 0, 0, ext_var_binds)


def _if_descr_discovery_response(if_indexes: list[int]):
    """`ifDescr` subtree'sinin bir GETBULK turunu simüle eder."""
    base = INTERFACE_OIDS["ifDescr"]
    var_binds = tuple(
        _vb(f"{base}.{i}", OctetString(f"iface-{i}")) for i in if_indexes
    )
    return (None, 0, 0, var_binds)


def _end_of_subtree_response():
    """ifDescr subtree'sinden çıkan, keşfi durduran bir sonraki kolon."""
    return (None, 0, 0, (_vb(INTERFACE_OIDS["ifAdminStatus"] + ".1", Integer32(1)),))


def _sequential_get(*responses):
    """Ardışık `slim.get` çağrılarına sırayla verilecek yanıtlar."""
    calls = {"n": 0}

    async def _side_effect(community, host, port, *var_binds, timeout, retries):
        idx = calls["n"]
        calls["n"] += 1
        response = responses[idx]
        if isinstance(response, Exception):
            raise response
        return response

    return _side_effect


@pytest.fixture(autouse=True)
def _clean_bandwidth_state():
    _LAST_SAMPLES.clear()
    yield
    _LAST_SAMPLES.clear()


@pytest.fixture(autouse=True)
def _community_env(monkeypatch):
    monkeypatch.setenv(_SECRET_ENV_VAR, _SECRET_VALUE)


def _no_interfaces_bulk():
    return AsyncMock(return_value=(None, 0, 0, ()))


# 1. Başarılı v2c GET
async def test_successful_v2c_get():
    profile = _profile()
    with (
        patch("app.snmp.client.Slim.get", new=AsyncMock(side_effect=_sequential_get(_system_response()))),
        patch("app.snmp.client.Slim.bulk", new=_no_interfaces_bulk()),
    ):
        result = await SNMPClient().poll_asset(profile, "10.0.9.1", profile.asset_id)

    assert result.status == "success"
    assert result.system is not None
    assert result.system.sys_name == "core-sw-01"


# 2. Birden fazla OID'li GET
async def test_multiple_oid_get():
    get_mock = AsyncMock(side_effect=_sequential_get(_system_response()))
    with (
        patch("app.snmp.client.Slim.get", new=get_mock),
        patch("app.snmp.client.Slim.bulk", new=_no_interfaces_bulk()),
    ):
        await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    first_call_var_binds = get_mock.call_args_list[0].args[3:]
    assert len(first_call_var_binds) == len(SYSTEM_OIDS)


# 3. Timeout
async def test_timeout():
    get_mock = AsyncMock(return_value=(errind.requestTimedOut, 0, 0, ()))
    with patch("app.snmp.client.Slim.get", new=get_mock):
        result = await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    assert result.status == "timeout"
    assert result.system is None


# 4. Retry (timeout/retries değerleri gerçek çağrıya iletiliyor mu)
async def test_retry_parameters_forwarded():
    profile = _profile(timeout_seconds=5.0, retries=3)
    get_mock = AsyncMock(side_effect=_sequential_get(_system_response()))
    with (
        patch("app.snmp.client.Slim.get", new=get_mock),
        patch("app.snmp.client.Slim.bulk", new=_no_interfaces_bulk()),
    ):
        await SNMPClient().poll_asset(profile, "10.0.9.1", uuid4())

    kwargs = get_mock.call_args_list[0].kwargs
    assert kwargs["timeout"] == 5.0
    assert kwargs["retries"] == 3


# 5. Kimlik doğrulama hatası
async def test_authentication_failure():
    get_mock = AsyncMock(return_value=(errind.authenticationFailure, 0, 0, ()))
    with patch("app.snmp.client.Slim.get", new=get_mock):
        result = await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    assert result.status == "authentication_failed"


# 6. Ulaşılamayan cihaz
async def test_unreachable_device():
    get_mock = AsyncMock(return_value=(errind.emptyResponse, 0, 0, ()))
    with patch("app.snmp.client.Slim.get", new=get_mock):
        result = await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    assert result.status == "unreachable"


# 7. Bozuk (malformed) yanıt — errorStatus != 0
async def test_malformed_response_error_status():
    get_mock = AsyncMock(return_value=(None, 2, 1, ()))
    with patch("app.snmp.client.Slim.get", new=get_mock):
        result = await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    assert result.status == "unreachable"
    assert result.system is None
    assert "errorStatus" in result.error


# 8. sysName parsing
async def test_sys_name_parsing():
    with (
        patch(
            "app.snmp.client.Slim.get",
            new=AsyncMock(side_effect=_sequential_get(_system_response(sysName=OctetString("edge-router-07")))),
        ),
        patch("app.snmp.client.Slim.bulk", new=_no_interfaces_bulk()),
    ):
        result = await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    assert result.system.sys_name == "edge-router-07"


# 9. sysUpTime parsing
async def test_sys_uptime_parsing():
    with (
        patch(
            "app.snmp.client.Slim.get",
            new=AsyncMock(side_effect=_sequential_get(_system_response(sysUpTime=TimeTicks(9_988_776)))),
        ),
        patch("app.snmp.client.Slim.bulk", new=_no_interfaces_bulk()),
    ):
        result = await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    assert result.system.sys_uptime_ticks == 9_988_776


# 10. Interface parsing
async def test_interface_parsing():
    get_mock = AsyncMock(
        side_effect=_sequential_get(_system_response(), *_interface_response(if_index=1))
    )
    bulk_mock = AsyncMock(return_value=_if_descr_discovery_response([1]))
    with patch("app.snmp.client.Slim.get", new=get_mock), patch("app.snmp.client.Slim.bulk", new=bulk_mock):
        result = await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    assert result.status == "success"
    assert len(result.interfaces) == 1
    iface = result.interfaces[0]
    assert iface.if_index == 1
    assert iface.if_name == "Gi0/1"
    assert iface.if_descr == "GigabitEthernet0/1"


# 11. Interface admin/oper status eşlemesi
async def test_interface_admin_oper_status_mapping():
    get_mock = AsyncMock(
        side_effect=_sequential_get(
            _system_response(),
            *_interface_response(if_index=1, ifAdminStatus=Integer32(1), ifOperStatus=Integer32(2)),
        )
    )
    bulk_mock = AsyncMock(return_value=_if_descr_discovery_response([1]))
    with patch("app.snmp.client.Slim.get", new=get_mock), patch("app.snmp.client.Slim.bulk", new=bulk_mock):
        result = await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    iface = result.interfaces[0]
    assert iface.if_admin_status == "up"
    assert iface.if_oper_status == "down"


# 12. 64-bit sayaçlar tercih ediliyor
async def test_64bit_counters_preferred():
    get_mock = AsyncMock(
        side_effect=_sequential_get(
            _system_response(),
            *_interface_response(
                if_index=1,
                ifHCInOctets=Counter64(5_000_000_000),
                ifHCOutOctets=Counter64(6_000_000_000),
                ifInOctets=Counter32(123),
                ifOutOctets=Counter32(456),
            ),
        )
    )
    bulk_mock = AsyncMock(return_value=_if_descr_discovery_response([1]))
    with patch("app.snmp.client.Slim.get", new=get_mock), patch("app.snmp.client.Slim.bulk", new=bulk_mock):
        result = await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    iface = result.interfaces[0]
    assert iface.if_in_octets == 5_000_000_000
    assert iface.if_out_octets == 6_000_000_000
    assert iface.if_counters_64bit is True


# 21. ifInErrors/ifOutErrors parsing (Faz 26 — interface_error alert kuralı için)
async def test_interface_error_counters_parsed():
    get_mock = AsyncMock(
        side_effect=_sequential_get(
            _system_response(),
            *_interface_response(if_index=1, ifInErrors=Counter32(7), ifOutErrors=Counter32(2)),
        )
    )
    bulk_mock = AsyncMock(return_value=_if_descr_discovery_response([1]))
    with patch("app.snmp.client.Slim.get", new=get_mock), patch("app.snmp.client.Slim.bulk", new=bulk_mock):
        result = await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    iface = result.interfaces[0]
    assert iface.if_in_errors == 7
    assert iface.if_out_errors == 2


# 13. Bant genişliği hesabı (ikinci poll'dan itibaren)
async def test_bandwidth_calculation_on_second_poll():
    asset_id = uuid4()
    profile = _profile(asset_id=asset_id)

    with (
        patch("app.snmp.client.time.time", side_effect=[1_000.0, 1_001.0]),
        patch(
            "app.snmp.client.Slim.get",
            new=AsyncMock(
                side_effect=_sequential_get(
                    _system_response(),
                    *_interface_response(if_index=1, ifHCInOctets=Counter64(1_000_000), ifHCOutOctets=Counter64(2_000_000)),
                    _system_response(),
                    *_interface_response(if_index=1, ifHCInOctets=Counter64(2_000_000), ifHCOutOctets=Counter64(4_000_000)),
                )
            ),
        ),
        patch("app.snmp.client.Slim.bulk", new=AsyncMock(return_value=_if_descr_discovery_response([1]))),
    ):
        first = await SNMPClient().poll_asset(profile, "10.0.9.1", asset_id)
        second = await SNMPClient().poll_asset(profile, "10.0.9.1", asset_id)

    assert first.interfaces[0].if_in_bps is None
    assert second.interfaces[0].if_in_bps == pytest.approx(8_000_000.0)
    assert second.interfaces[0].if_out_bps == pytest.approx(16_000_000.0)


# 14. Counter rollover -> None (asla negatif/tahmini bir hız değil)
async def test_counter_rollover_returns_none_bandwidth():
    asset_id = uuid4()
    profile = _profile(asset_id=asset_id)

    with (
        patch("app.snmp.client.time.time", side_effect=[1_000.0, 1_001.0]),
        patch(
            "app.snmp.client.Slim.get",
            new=AsyncMock(
                side_effect=_sequential_get(
                    _system_response(),
                    *_interface_response(if_index=1, ifHCInOctets=Counter64(5_000_000)),
                    _system_response(),
                    *_interface_response(if_index=1, ifHCInOctets=Counter64(1_000)),  # rollover/restart
                )
            ),
        ),
        patch("app.snmp.client.Slim.bulk", new=AsyncMock(return_value=_if_descr_discovery_response([1]))),
    ):
        await SNMPClient().poll_asset(profile, "10.0.9.1", asset_id)
        second = await SNMPClient().poll_asset(profile, "10.0.9.1", asset_id)

    assert second.interfaces[0].if_in_bps is None


# 15. İlk poll davranışı — baseline yok, bps None
async def test_first_poll_has_no_bandwidth_baseline():
    get_mock = AsyncMock(
        side_effect=_sequential_get(_system_response(), *_interface_response(if_index=1))
    )
    bulk_mock = AsyncMock(return_value=_if_descr_discovery_response([1]))
    with patch("app.snmp.client.Slim.get", new=get_mock), patch("app.snmp.client.Slim.bulk", new=bulk_mock):
        result = await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    assert result.interfaces[0].if_in_bps is None
    assert result.interfaces[0].if_out_bps is None


# 16. Secret hiçbir log kaydında görünmez
async def test_secret_never_appears_in_logs(caplog):
    get_mock = AsyncMock(return_value=(errind.authenticationFailure, 0, 0, ()))
    with caplog.at_level(logging.DEBUG), patch("app.snmp.client.Slim.get", new=get_mock):
        await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    for record in caplog.records:
        assert _SECRET_VALUE not in record.getMessage()


# 17. Secret hiçbir API response'unda (model serileştirmesinde) görünmez
async def test_secret_never_appears_in_response_serialization():
    get_mock = AsyncMock(return_value=(errind.requestTimedOut, 0, 0, ()))
    with patch("app.snmp.client.Slim.get", new=get_mock):
        result = await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    serialized = result.model_dump_json()
    assert _SECRET_VALUE not in serialized

    success_get_mock = AsyncMock(side_effect=_sequential_get(_system_response()))
    with (
        patch("app.snmp.client.Slim.get", new=success_get_mock),
        patch("app.snmp.client.Slim.bulk", new=_no_interfaces_bulk()),
    ):
        ok_result = await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    assert _SECRET_VALUE not in ok_result.model_dump_json()


# 18. not_configured davranışı (community secret .env'de yoksa)
async def test_not_configured_when_secret_missing(monkeypatch):
    monkeypatch.delenv(_SECRET_ENV_VAR, raising=False)
    get_mock = AsyncMock()
    with patch("app.snmp.client.Slim.get", new=get_mock):
        result = await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    assert result.status == "not_configured"
    get_mock.assert_not_called()


# 19. Kısmi (partial) interface hatası
async def test_partial_interface_failure():
    get_mock = AsyncMock(
        side_effect=_sequential_get(
            _system_response(),
            *_interface_response(if_index=1),
            (errind.requestTimedOut, 0, 0, ()),  # ifIndex 2 için GET zaman aşımı
        )
    )
    bulk_mock = AsyncMock(return_value=_if_descr_discovery_response([1, 2]))
    with patch("app.snmp.client.Slim.get", new=get_mock), patch("app.snmp.client.Slim.bulk", new=bulk_mock):
        result = await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    assert result.status == "partial"
    assert len(result.interfaces) == 1
    assert result.interfaces[0].if_index == 1
    assert result.error is not None
    assert "ifIndex 2" in result.error


# 20. Bozuk OID yanıtı (tablo dışı/parse edilemeyen index) çökmeden atlanır
async def test_malformed_oid_in_discovery_is_skipped():
    base = INTERFACE_OIDS["ifDescr"]
    malformed_var_bind = _vb(f"{base}.1.99", OctetString("multi-dimensional-index"))
    valid_var_bind = _vb(f"{base}.2", OctetString("iface-2"))
    bulk_mock = AsyncMock(return_value=(None, 0, 0, (malformed_var_bind, valid_var_bind)))
    get_mock = AsyncMock(
        side_effect=_sequential_get(_system_response(), *_interface_response(if_index=2))
    )
    with patch("app.snmp.client.Slim.get", new=get_mock), patch("app.snmp.client.Slim.bulk", new=bulk_mock):
        result = await SNMPClient().poll_asset(_profile(), "10.0.9.1", uuid4())

    assert result.status == "success"
    assert [iface.if_index for iface in result.interfaces] == [2]
