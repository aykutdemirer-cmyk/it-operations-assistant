"""Gerçek SNMP client — SNMPv2c ve SNMPv3.

pysnmp'nin yüksek seviye API'leri üzerine ince bir katman: v2c için
`pysnmp.hlapi.v1arch.asyncio.slim.Slim`, v3 için `pysnmp.hlapi.v3arch.
asyncio` (`SnmpEngine`/`UsmUserData`/`get_cmd`/`bulk_cmd` — v3arch'ta
`Slim` benzeri bir sarmalayıcı yok). İki versiyon da aynı `_Transport`
arayüzü (`.get(*var_binds)` / `.bulk(non_reps, max_reps, *var_binds)`)
üzerinden `_get_system_info`/`_discover_if_indexes`/`_get_interface_info`
tarafından **tek bir** ortak parsing/orkestrasyon koduyla kullanılır —
MIB parsing mantığı iki versiyon arasında asla tekrar edilmez (bkz. Faz
22.4: "duplicate component oluşturma").

Katman sorumluluğu net: bu modül SADECE gerçek ağ/pysnmp ile konuşur ve
sonucu var olan `SNMPPollResult`/`SystemInfo`/`InterfaceInfo`
modellerine çevirir. Hiçbir pysnmp-özel tip (ErrorIndication, pyasn1
tipleri) bu modülün dışına sızmaz; hiçbir exception mesajı credential
DEĞERİ içermez (yalnızca `community_ref`/`username` gibi bir İSİM
loglanabilir, gerçek secret değeri asla — bkz. `secrets.py`)."""

import logging
import time
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from pysnmp.error import PySnmpError
from pysnmp.hlapi.v1arch.asyncio import ObjectIdentity, ObjectType
from pysnmp.hlapi.v1arch.asyncio.slim import Slim
from pysnmp.hlapi.v3arch.asyncio import (
    ContextData,
    SnmpEngine,
    UdpTransportTarget as V3UdpTransportTarget,
    UsmUserData,
    bulk_cmd as v3_bulk_cmd,
    get_cmd as v3_get_cmd,
    usmAesCfb128Protocol,
    usmAesCfb192Protocol,
    usmAesCfb256Protocol,
    usmDESPrivProtocol,
    usmHMAC128SHA224AuthProtocol,
    usmHMAC192SHA256AuthProtocol,
    usmHMAC256SHA384AuthProtocol,
    usmHMAC384SHA512AuthProtocol,
    usmHMACMD5AuthProtocol,
    usmHMACSHAAuthProtocol,
)
from pysnmp.proto import errind, rfc1905

from app.snmp.bandwidth import CounterSample, calculate_bandwidth_bps
from app.snmp.credentials import SNMPAuthProtocol, SNMPPrivProtocol, SNMPProfile
from app.snmp.exceptions import (
    SNMPAuthenticationError,
    SNMPError,
    SNMPProtocolError,
    SNMPTimeoutError,
    SNMPUnavailableError,
)
from app.snmp.models import IfStatus, InterfaceInfo, SNMPPollResult, SystemInfo
from app.snmp.oid_map import (
    HR_PROCESSOR_LOAD_BASE_OID,
    HR_STORAGE_ALLOC_UNITS_BASE_OID,
    HR_STORAGE_RAM_TYPE_OID,
    HR_STORAGE_SIZE_BASE_OID,
    HR_STORAGE_TYPE_BASE_OID,
    HR_STORAGE_USED_BASE_OID,
    INTERFACE_OIDS,
    SYSTEM_OIDS,
)
from app.snmp.secrets import resolve_secret

logger = logging.getLogger(__name__)

# ifAdminStatus / ifOperStatus (IF-MIB, RFC 2863) tamsayı -> isim eşlemesi.
_IF_STATUS_MAP: dict[int, IfStatus] = {
    1: "up",
    2: "down",
    3: "testing",
    4: "unknown",
    5: "dormant",
    6: "notPresent",
    7: "lowerLayerDown",
}

# ifDescr (1.3.6.1.2.1.2.2.1.2) subtree'sini GETBULK ile dolaşıp mevcut
# `ifIndex` kümesini keşfetmek için kullanılır — her interface kolonunu
# ayrı ayrı bulk-walk etmek yerine tek bir keşif + kolon başına GET.
_IF_INDEX_DISCOVERY_OID = INTERFACE_OIDS["ifDescr"]

# Bir önceki poll'un in/out octet örnekleri — bant genişliği hesaplamak
# için gereken tek "stateful" parça. Süreç-içi (in-memory) önbellek:
# backend yeniden başladığında sıfırlanır, bu durumda bir sonraki poll
# yine "ilk poll" gibi davranır ve bps `None` döner. Kalıcı bir depolama
# katmanı eklemeden (bkz. `profile_store.py`) en basit doğru davranış
# budur; çoklu-worker/çoklu-process bir dağıtımda paylaşılmaz — bu
# bilinen bir sınırlamadır (bkz. docs).
_LAST_SAMPLES: dict[tuple[UUID, int, str], CounterSample] = {}

_MAX_REPETITIONS = 20
_MAX_BULK_ROUNDS = 50  # sonsuz döngüye karşı güvenlik sınırı

# SNMPv3 USM auth/priv protokol isimleri -> pysnmp OID sabitleri. MD5/DES
# yalnızca eski ajan uyumluluğu için burada duruyor — kod hiçbir yerde
# bunları varsayılan (default) seçmez, `SNMPProfile.auth_protocol`/
# `priv_protocol` her zaman açıkça seçilmesi gereken zorunlu alanlardır
# (bkz. `credentials.py`).
_AUTH_PROTOCOL_MAP: dict[SNMPAuthProtocol, object] = {
    "MD5": usmHMACMD5AuthProtocol,
    "SHA": usmHMACSHAAuthProtocol,
    "SHA224": usmHMAC128SHA224AuthProtocol,
    "SHA256": usmHMAC192SHA256AuthProtocol,
    "SHA384": usmHMAC256SHA384AuthProtocol,
    "SHA512": usmHMAC384SHA512AuthProtocol,
}
_PRIV_PROTOCOL_MAP: dict[SNMPPrivProtocol, object] = {
    "DES": usmDESPrivProtocol,
    "AES": usmAesCfb128Protocol,
    "AES192": usmAesCfb192Protocol,
    "AES256": usmAesCfb256Protocol,
}

_SNMPResponse = tuple[object, object, object, tuple]


class _Transport(Protocol):
    """v2c ve v3 için ortak GET/GETBULK arayüzü — `timeout`/`retries`
    (v2c) veya hazır transport target (v3) her transport'un kendi
    kurulumunda bağlanır, bu arayüz yalnızca varbind alışverişini
    soyutlar."""

    async def get(self, *var_binds: ObjectType) -> _SNMPResponse: ...

    async def bulk(
        self, non_repeaters: int, max_repetitions: int, *var_binds: ObjectType
    ) -> _SNMPResponse: ...


class _V2cTransport:
    def __init__(self, slim: Slim, community: str, host: str, port: int, timeout: float, retries: int):
        self._slim = slim
        self._community = community
        self._host = host
        self._port = port
        self._timeout = timeout
        self._retries = retries

    async def get(self, *var_binds: ObjectType) -> _SNMPResponse:
        return await self._slim.get(
            self._community, self._host, self._port, *var_binds,
            timeout=self._timeout, retries=self._retries,
        )

    async def bulk(self, non_repeaters: int, max_repetitions: int, *var_binds: ObjectType) -> _SNMPResponse:
        return await self._slim.bulk(
            self._community, self._host, self._port, non_repeaters, max_repetitions, *var_binds,
            timeout=self._timeout, retries=self._retries,
        )


class _V3Transport:
    def __init__(self, engine: SnmpEngine, usm_user_data: UsmUserData, transport_target, context_data: ContextData):
        self._engine = engine
        self._usm_user_data = usm_user_data
        self._transport_target = transport_target
        self._context_data = context_data

    async def get(self, *var_binds: ObjectType) -> _SNMPResponse:
        return await v3_get_cmd(
            self._engine, self._usm_user_data, self._transport_target, self._context_data, *var_binds
        )

    async def bulk(self, non_repeaters: int, max_repetitions: int, *var_binds: ObjectType) -> _SNMPResponse:
        return await v3_bulk_cmd(
            self._engine, self._usm_user_data, self._transport_target, self._context_data,
            non_repeaters, max_repetitions, *var_binds,
        )


def _translate_error_indication(error_indication: errind.ErrorIndication) -> SNMPError:
    """pysnmp `ErrorIndication` örneğini kendi hiyerarşimize çevirir.

    Mesaj asla credential DEĞERİ içermez — yalnızca hata sınıfının adı
    ve (varsa) host/port gibi credential OLMAYAN bağlam."""
    if isinstance(error_indication, errind.RequestTimedOut):
        return SNMPTimeoutError("SNMP isteği zaman aşımına uğradı")
    if isinstance(
        error_indication,
        (
            errind.AuthenticationError,
            errind.AuthenticationFailure,
            errind.UnknownCommunityName,
            errind.UnknownUserName,
            errind.UnsupportedAuthProtocol,
            errind.UnsupportedPrivProtocol,
            errind.WrongDigest,
            # SNMPv3/USM'e özgü kimlik doğrulama/gizlilik reddi türleri:
            errind.DecryptionError,  # yanlış priv key
            errind.NotInTimeWindow,  # USM zaman senkronizasyonu reddi
            errind.UnknownEngineID,  # v3 discovery/engine ID uyuşmazlığı
        ),
    ):
        return SNMPAuthenticationError("SNMP kimlik doğrulama reddedildi")
    return SNMPUnavailableError(
        f"SNMP hedefine ulaşılamadı ({error_indication.__class__.__name__})"
    )


def _is_missing_value(value) -> bool:
    return isinstance(value, (rfc1905.NoSuchObject, rfc1905.NoSuchInstance, rfc1905.EndOfMibView))


def _as_str(value) -> str | None:
    if value is None or _is_missing_value(value):
        return None
    return str(value)


def _as_int(value) -> int | None:
    if value is None or _is_missing_value(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_if_status(value) -> IfStatus | None:
    raw = _as_int(value)
    if raw is None:
        return None
    return _IF_STATUS_MAP.get(raw)


class SNMPClient:
    """Bir asset'i gerçek SNMP (v2c veya v3) ile poll etmek için tek
    giriş noktası.

    Kullanım: `await SNMPClient().poll_asset(profile, host, asset_id)`."""

    async def poll_asset(
        self, profile: SNMPProfile, host: str, asset_id: UUID
    ) -> SNMPPollResult:
        started = time.monotonic()
        polled_at = _now()

        logger.debug(
            "SNMP poll başlıyor: asset_id=%s host=%s port=%s version=%s",
            asset_id, host, profile.port, profile.version,
        )

        if profile.version == "v2c":
            return await self._poll_v2c(profile, host, asset_id, polled_at, started)
        if profile.version == "v3":
            return await self._poll_v3(profile, host, asset_id, polled_at, started)
        raise SNMPProtocolError(f"Desteklenmeyen SNMP versiyonu: {profile.version}")

    async def _poll_v2c(
        self, profile: SNMPProfile, host: str, asset_id: UUID, polled_at: datetime, started: float
    ) -> SNMPPollResult:
        community = resolve_secret(profile.community_ref, allow_literal_fallback=True)
        if not community:
            # `allow_literal_fallback=True` iken `community_ref` boş/None
            # OLMADIĞI sürece asla None dönmez (bulunamazsa metnin
            # kendisi kullanılır) — bu dal artık yalnızca community
            # string hiç girilmemişse tetiklenir.
            return self._not_configured_result(
                asset_id, polled_at,
                "Community string girilmemiş.",
            )

        with Slim(version=2) as slim:
            transport = _V2cTransport(
                slim, community, host, profile.port, profile.timeout_seconds, profile.retries
            )
            return await self._poll_with_transport(transport, asset_id, polled_at, started, host)

    async def _poll_v3(
        self, profile: SNMPProfile, host: str, asset_id: UUID, polled_at: datetime, started: float
    ) -> SNMPPollResult:
        resolved = self._resolve_v3_credentials(profile)
        if resolved is None:
            return self._not_configured_result(
                asset_id, polled_at,
                "SNMPv3 credential(ler)i .env üzerinden çözülemedi "
                "(username/auth_credential_ref/priv_credential_ref).",
            )
        username, auth_key, priv_key = resolved

        try:
            usm_user_data = self._build_usm_user_data(
                username, auth_key, profile.auth_protocol, priv_key, profile.priv_protocol
            )
        except PySnmpError as exc:
            # Ör. "Privacy implies authenticity" — kurulum anında,
            # ağa hiç çıkmadan fırlar. Mesaj yalnızca sınıf adını taşır.
            return SNMPPollResult(
                asset_id=asset_id,
                polled_at=polled_at,
                status="unreachable",
                error=f"SNMPv3 kimlik verisi kurulamadı ({exc.__class__.__name__}).",
                duration_ms=_elapsed_ms(started),
            )

        engine = SnmpEngine()
        try:
            transport_target = await V3UdpTransportTarget.create(
                (host, profile.port), profile.timeout_seconds, profile.retries
            )
            transport = _V3Transport(engine, usm_user_data, transport_target, ContextData())
            return await self._poll_with_transport(transport, asset_id, polled_at, started, host)
        finally:
            try:
                engine.close_dispatcher()
            except Exception:
                logger.debug("SNMPv3 engine kapatılırken hata oluştu (asset_id=%s)", asset_id)

    @staticmethod
    def _resolve_v3_credentials(profile: SNMPProfile) -> tuple[str, str | None, str | None] | None:
        """Gerçek username/auth-key/priv-key değerlerini `.env`'den
        çözer. Herhangi bir zorunlu secret çözülemezse `None` — bu,
        `not_configured` sonucuna çevrilir. Dönen değerler asla
        loglanmaz/döndürülmez, yalnızca `UsmUserData` kurmak için
        kullanılır."""
        if not profile.username:
            return None

        auth_key: str | None = None
        if profile.auth_protocol:
            auth_key = resolve_secret(profile.auth_credential_ref)
            if not auth_key:
                return None

        priv_key: str | None = None
        if profile.priv_protocol:
            priv_key = resolve_secret(profile.priv_credential_ref)
            if not priv_key:
                return None

        return profile.username, auth_key, priv_key

    @staticmethod
    def _build_usm_user_data(
        username: str,
        auth_key: str | None,
        auth_protocol: SNMPAuthProtocol | None,
        priv_key: str | None,
        priv_protocol: SNMPPrivProtocol | None,
    ) -> UsmUserData:
        """`UsmUserData` her zaman `authKey`/`authProtocol` ve
        `privKey`/`privProtocol`'ü BİRLİKTE, açıkça alır — hiçbir zaman
        yalnızca key verilip protocol'ü pysnmp'nin kendi varsayılanına
        (MD5/DES!) bırakılmaz (bkz. modül docstring'i ve
        `docs/decisions.md` §10.2)."""
        auth_protocol_oid = _AUTH_PROTOCOL_MAP.get(auth_protocol) if auth_protocol else None
        priv_protocol_oid = _PRIV_PROTOCOL_MAP.get(priv_protocol) if priv_protocol else None
        return UsmUserData(
            userName=username,
            authKey=auth_key,
            authProtocol=auth_protocol_oid,
            privKey=priv_key,
            privProtocol=priv_protocol_oid,
        )

    def _not_configured_result(self, asset_id: UUID, polled_at: datetime, error: str) -> SNMPPollResult:
        return SNMPPollResult(asset_id=asset_id, polled_at=polled_at, status="not_configured", error=error)

    async def _poll_with_transport(
        self, transport: _Transport, asset_id: UUID, polled_at: datetime, started: float, host: str
    ) -> SNMPPollResult:
        """v2c/v3 ortak akışı: system GET -> interface keşfi -> her
        interface için GET -> `SNMPPollResult`. Versiyon-özel hiçbir şey
        bilmez, yalnızca `_Transport` arayüzünü kullanır."""
        try:
            system = await self._get_system_info(transport)
        except SNMPError as exc:
            status = _status_for_error(exc)
            logger.warning(
                "SNMP poll başarısız: asset_id=%s host=%s status=%s (%s)",
                asset_id, host, status, exc.__class__.__name__,
            )
            return SNMPPollResult(
                asset_id=asset_id, polled_at=polled_at, status=status, error=str(exc),
                duration_ms=_elapsed_ms(started),
            )

        # HOST-RESOURCES-MIB (CPU/Bellek) — BİLİNÇLİ olarak system GET'in
        # kendi try/except'inden AYRI: çoğu switch/router/firewall bu
        # MIB'i hiç desteklemez, bu asla bir poll hatası SAYILMAZ,
        # yalnızca alanlar `None` kalır (bkz. oid_map.py docstring'i).
        try:
            cpu_percent, memory_used_bytes, memory_total_bytes = await self._get_cpu_memory_info(transport)
        except Exception:  # noqa: BLE001 — HOST-RESOURCES-MIB opsiyonel, hiçbir hata poll'u durdurmaz
            logger.debug(
                "HOST-RESOURCES-MIB (CPU/Bellek) desteklenmiyor gibi görünüyor (asset_id=%s)", asset_id
            )
            cpu_percent, memory_used_bytes, memory_total_bytes = None, None, None
        system = system.model_copy(
            update={
                "cpu_percent": cpu_percent,
                "memory_used_bytes": memory_used_bytes,
                "memory_total_bytes": memory_total_bytes,
            }
        )

        try:
            if_indexes = await self._discover_if_indexes(transport)
        except SNMPError as exc:
            # System başarılı ama interface keşfi başarısız oldu —
            # kısmi (partial) sonuç: system verisi gerçek, interfaces
            # boş, `error` neyin eksik olduğunu açıklar.
            return SNMPPollResult(
                asset_id=asset_id, polled_at=polled_at, status="partial", system=system, interfaces=[],
                error=f"Interface keşfi başarısız: {exc}", duration_ms=_elapsed_ms(started),
            )

        interfaces: list[InterfaceInfo] = []
        interface_errors: list[str] = []
        for if_index in if_indexes:
            try:
                interfaces.append(await self._get_interface_info(transport, if_index, asset_id))
            except SNMPError as exc:
                interface_errors.append(f"ifIndex {if_index}: {exc}")

        status = "partial" if interface_errors else "success"
        error = "; ".join(interface_errors) if interface_errors else None
        logger.info(
            "SNMP poll tamamlandı: asset_id=%s host=%s status=%s interfaces=%d duration_ms=%.1f",
            asset_id, host, status, len(interfaces), _elapsed_ms(started),
        )
        return SNMPPollResult(
            asset_id=asset_id, polled_at=polled_at, status=status, system=system,
            interfaces=interfaces, error=error, duration_ms=_elapsed_ms(started),
        )

    async def _get_system_info(self, transport: _Transport) -> SystemInfo:
        names = list(SYSTEM_OIDS.keys())
        var_binds_in = [ObjectType(ObjectIdentity(SYSTEM_OIDS[name])) for name in names]

        error_indication, error_status, _error_index, var_binds = await transport.get(*var_binds_in)
        if error_indication is not None:
            raise _translate_error_indication(error_indication)
        if error_status:
            raise SNMPProtocolError(f"system GET errorStatus={error_status}")

        values = {name: vb[1] for name, vb in zip(names, var_binds)}
        return SystemInfo(
            sys_descr=_as_str(values.get("sysDescr")),
            sys_object_id=_as_str(values.get("sysObjectID")),
            sys_uptime_ticks=_as_int(values.get("sysUpTime")),
            sys_name=_as_str(values.get("sysName")),
        )

    async def _discover_if_indexes(self, transport: _Transport) -> list[int]:
        base_oid = _IF_INDEX_DISCOVERY_OID
        current_oid = base_oid
        seen_oids: set[str] = set()
        if_indexes: list[int] = []

        for _ in range(_MAX_BULK_ROUNDS):
            error_indication, error_status, _error_index, var_binds = await transport.bulk(
                0, _MAX_REPETITIONS, ObjectType(ObjectIdentity(current_oid))
            )
            if error_indication is not None:
                raise _translate_error_indication(error_indication)
            if error_status:
                raise SNMPProtocolError(f"ifDescr GETBULK errorStatus={error_status}")
            if not var_binds:
                break

            advanced = False
            for var_bind in var_binds:
                oid_str = str(var_bind[0])
                if not oid_str.startswith(base_oid + "."):
                    continue
                if _is_missing_value(var_bind[1]):
                    continue
                if oid_str in seen_oids:
                    continue
                seen_oids.add(oid_str)
                current_oid = oid_str
                advanced = True
                suffix = oid_str[len(base_oid) + 1 :]
                try:
                    if_indexes.append(int(suffix))
                except ValueError:
                    continue

            if not advanced:
                break

        return if_indexes

    async def _bulk_walk(self, transport: _Transport, base_oid: str) -> list[tuple[str, object]]:
        """`base_oid` alt ağacını GETBULK ile sondan sona dolaşır,
        `(tam_oid, ham_değer)` çiftlerini döner — `_discover_if_indexes`
        ile AYNI "ilerleme yoksa dur" + sonsuz-döngü güvenlik sınırı
        (`_MAX_BULK_ROUNDS`) mantığını, farklı bir subtree için
        genelleştirir (HOST-RESOURCES-MIB tabloları — bkz.
        `_get_cpu_percent`/`_get_memory_bytes`)."""
        current_oid = base_oid
        seen: set[str] = set()
        out: list[tuple[str, object]] = []

        for _ in range(_MAX_BULK_ROUNDS):
            error_indication, error_status, _error_index, var_binds = await transport.bulk(
                0, _MAX_REPETITIONS, ObjectType(ObjectIdentity(current_oid))
            )
            if error_indication is not None:
                raise _translate_error_indication(error_indication)
            if error_status:
                raise SNMPProtocolError(f"{base_oid} GETBULK errorStatus={error_status}")
            if not var_binds:
                break

            advanced = False
            for var_bind in var_binds:
                oid_str = str(var_bind[0])
                if not oid_str.startswith(base_oid + "."):
                    continue
                if _is_missing_value(var_bind[1]):
                    continue
                if oid_str in seen:
                    continue
                seen.add(oid_str)
                current_oid = oid_str
                advanced = True
                out.append((oid_str, var_bind[1]))

            if not advanced:
                break

        return out

    async def _get_cpu_memory_info(
        self, transport: _Transport
    ) -> tuple[float | None, int | None, int | None]:
        """HOST-RESOURCES-MIB — bkz. `oid_map.py`. Çağıran taraf
        (`_poll_with_transport`) bunu her zaman geniş bir `try/except`
        içinde çağırır; burada da her alt adım kendi içinde
        `SNMPError`'ı yutup `None` döner — bu MIB'i implemente
        ETMEYEN (çoğu switch/router/firewall) bir ajanda asla poll'un
        genel `status`'unu etkilemez."""
        cpu_percent = await self._get_cpu_percent(transport)
        memory_used_bytes, memory_total_bytes = await self._get_memory_bytes(transport)
        return cpu_percent, memory_used_bytes, memory_total_bytes

    async def _get_cpu_percent(self, transport: _Transport) -> float | None:
        try:
            entries = await self._bulk_walk(transport, HR_PROCESSOR_LOAD_BASE_OID)
        except SNMPError:
            return None
        loads = [load for _, raw in entries if (load := _as_int(raw)) is not None]
        if not loads:
            return None
        # Birden fazla çekirdek/işlemci varsa ortalaması — tek bir
        # değer UYDURULMAZ, gerçekten dönen tüm `hrProcessorLoad`
        # satırlarının aritmetik ortalamasıdır.
        return sum(loads) / len(loads)

    async def _get_memory_bytes(self, transport: _Transport) -> tuple[int | None, int | None]:
        try:
            type_entries = await self._bulk_walk(transport, HR_STORAGE_TYPE_BASE_OID)
        except SNMPError:
            return None, None

        ram_index: str | None = None
        for oid_str, raw in type_entries:
            if _as_str(raw) == HR_STORAGE_RAM_TYPE_OID:
                ram_index = oid_str[len(HR_STORAGE_TYPE_BASE_OID) + 1 :]
                break
        if ram_index is None:
            # Ajan hrStorageTable'ı desteklemiyor VEYA RAM satırı yok —
            # ikisi de dürüstçe "veri yok" demek, hata DEĞİL.
            return None, None

        var_binds_in = [
            ObjectType(ObjectIdentity(f"{HR_STORAGE_SIZE_BASE_OID}.{ram_index}")),
            ObjectType(ObjectIdentity(f"{HR_STORAGE_USED_BASE_OID}.{ram_index}")),
            ObjectType(ObjectIdentity(f"{HR_STORAGE_ALLOC_UNITS_BASE_OID}.{ram_index}")),
        ]
        error_indication, error_status, _error_index, var_binds = await transport.get(*var_binds_in)
        if error_indication is not None or error_status:
            return None, None

        size_units = _as_int(var_binds[0][1])
        used_units = _as_int(var_binds[1][1])
        alloc_units = _as_int(var_binds[2][1])
        if size_units is None or used_units is None or alloc_units is None or alloc_units <= 0:
            return None, None

        return used_units * alloc_units, size_units * alloc_units

    async def _get_interface_info(self, transport: _Transport, if_index: int, asset_id: UUID) -> InterfaceInfo:
        # `ifTable` (MIB-II, RFC 1213) ve `ifXTable` (IF-MIB uzantısı, RFC
        # 2863) AYRI GET'lerle sorgulanır — tek bir kombine GET içinde
        # ajan `ifXTable`'ı (ifName/ifHCInOctets/ifHCOutOctets) hiç
        # desteklemiyorsa (ör. Windows'un yerleşik SNMP servisi — yalnızca
        # eski MIB-II implementasyonu, ifXTable YOK) tüm PDU tek bir
        # `noSuchName` ile başarısız olabiliyordu ve bu OID'lerin
        # docstring'de vaat edilen "yoksa 32-bit'e düş" davranışı hiç
        # ÇALIŞMIYORDU — gerçek bir cihazda (bu makinenin kendi Windows
        # SNMP servisi) YAKALANDI. `ifXTable` GET'i artık BAĞIMSIZ hata
        # yönetimine sahip: başarısız olursa yalnızca o alanlar `None`
        # kalır, `ifTable`'daki 32-bit sayaçlara düşülür — tüm interface
        # sorgusu İPTAL EDİLMEZ.
        core_names = [name for name in INTERFACE_OIDS if name not in ("ifName", "ifHCInOctets", "ifHCOutOctets")]
        core_var_binds_in = [
            ObjectType(ObjectIdentity(f"{INTERFACE_OIDS[name]}.{if_index}")) for name in core_names
        ]

        error_indication, error_status, _error_index, var_binds = await transport.get(*core_var_binds_in)
        if error_indication is not None:
            raise _translate_error_indication(error_indication)
        if error_status:
            raise SNMPProtocolError(f"interface GET errorStatus={error_status} (ifIndex {if_index})")

        values = {name: vb[1] for name, vb in zip(core_names, var_binds)}

        ext_names = ["ifName", "ifHCInOctets", "ifHCOutOctets"]
        ext_var_binds_in = [
            ObjectType(ObjectIdentity(f"{INTERFACE_OIDS[name]}.{if_index}")) for name in ext_names
        ]
        try:
            ext_error_indication, ext_error_status, _ext_error_index, ext_var_binds = await transport.get(
                *ext_var_binds_in
            )
            if ext_error_indication is None and not ext_error_status:
                values.update({name: vb[1] for name, vb in zip(ext_names, ext_var_binds)})
            else:
                logger.debug(
                    "ifXTable desteklenmiyor gibi görünüyor (ifIndex %s) — 32-bit sayaçlara düşülüyor",
                    if_index,
                )
        except SNMPError:
            logger.debug(
                "ifXTable GET başarısız (ifIndex %s) — 32-bit sayaçlara düşülüyor", if_index
            )

        hc_in = _as_int(values.get("ifHCInOctets"))
        hc_out = _as_int(values.get("ifHCOutOctets"))
        uses_64bit = hc_in is not None or hc_out is not None
        in_octets = hc_in if hc_in is not None else _as_int(values.get("ifInOctets"))
        out_octets = hc_out if hc_out is not None else _as_int(values.get("ifOutOctets"))

        in_bps, out_bps = self._compute_bandwidth(asset_id, if_index, in_octets, out_octets)

        return InterfaceInfo(
            if_index=if_index,
            if_name=_as_str(values.get("ifName")),
            if_descr=_as_str(values.get("ifDescr")),
            if_admin_status=_as_if_status(values.get("ifAdminStatus")),
            if_oper_status=_as_if_status(values.get("ifOperStatus")),
            if_speed_bps=_as_int(values.get("ifSpeed")),
            if_in_octets=in_octets,
            if_out_octets=out_octets,
            if_counters_64bit=uses_64bit if (in_octets is not None or out_octets is not None) else None,
            if_in_bps=in_bps,
            if_out_bps=out_bps,
            if_in_errors=_as_int(values.get("ifInErrors")),
            if_out_errors=_as_int(values.get("ifOutErrors")),
        )

    def _compute_bandwidth(
        self, asset_id: UUID, if_index: int, in_octets: int | None, out_octets: int | None
    ) -> tuple[float | None, float | None]:
        now_ms = time.time() * 1000
        in_key = (asset_id, if_index, "in")
        out_key = (asset_id, if_index, "out")

        in_bps = self._compute_direction_bandwidth(in_key, in_octets, now_ms)
        out_bps = self._compute_direction_bandwidth(out_key, out_octets, now_ms)
        return in_bps, out_bps

    def _compute_direction_bandwidth(
        self, key: tuple[UUID, int, str], octets: int | None, now_ms: float
    ) -> float | None:
        if octets is None:
            return None
        current = CounterSample(octets=octets, timestamp_ms=now_ms)
        previous = _LAST_SAMPLES.get(key)
        _LAST_SAMPLES[key] = current
        if previous is None:
            # İlk poll — henüz baseline yok, bps hesaplanamaz.
            return None
        return calculate_bandwidth_bps(previous, current)


def _status_for_error(exc: SNMPError) -> str:
    if isinstance(exc, SNMPTimeoutError):
        return "timeout"
    if isinstance(exc, SNMPAuthenticationError):
        return "authentication_failed"
    if isinstance(exc, SNMPUnavailableError):
        return "unreachable"
    return "unreachable"


def _elapsed_ms(started: float) -> float:
    return (time.monotonic() - started) * 1000


def _now() -> datetime:
    return datetime.now(timezone.utc)
