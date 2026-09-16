"""SNMP Profile Configuration Center — servis (orkestrasyon) katmanı
(Faz 29). Route'lar ile `app/db/snmp_profiles.py` arasında; secret
çözümleme durumunu hesaplar, gerçek "Test Connection" akışını mevcut
`SNMPClient`'ı (değiştirilmeden) kullanarak yürütür."""

import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import asyncpg
from pydantic import BaseModel

from app.db import asset_snmp_profiles as asset_profiles_repo
from app.db import assets as assets_repo
from app.db import snmp_profiles as profiles_repo
from app.snmp.client import SNMPClient
from app.snmp.exceptions import SNMPError
from app.snmp.models import SystemInfo
from app.snmp.profile_config import (
    SNMPProfileResponse,
    SNMPProfileWriteRequest,
    row_to_domain_profile,
    row_to_response,
)
from app.snmp.secrets import resolve_secret

# `sys_descr` içinde arananlar — YALNIZCA cihazın KENDİSİNİN gerçekten
# döndürdüğü metinden (uydurma yok). Sıra ÖNEMLİ: daha spesifik
# terimler (ör. "firewall") daha genel olanlardan (ör. "router") ÖNCE
# kontrol edilir. Hiçbiri eşleşmezse dürüstçe `"network_device"` —
# port taraması yapılmadığı için "server"/"workstation" gibi host
# sınıfları burada ASLA tahmin edilmez.
_SYS_DESCR_DEVICE_TYPE_HINTS: list[tuple[str, str]] = [
    ("fortios", "firewall"),
    ("fortigate", "firewall"),
    ("pfsense", "firewall"),
    ("palo alto", "firewall"),
    ("pan-os", "firewall"),
    ("asa", "firewall"),
    ("firewall", "firewall"),
    ("catalyst", "switch"),
    ("nx-os", "switch"),
    ("switch", "switch"),
    ("ios-xe", "router"),
    ("ios software", "router"),
    ("junos", "router"),
    ("routeros", "router"),
    ("router", "router"),
]


# Profil ADI da (kullanıcının kendi verdiği, GERÇEK bir isim — ör.
# "FW", "Core Switch") ikinci bir dürüst sinyal olarak kullanılır;
# `sys_descr` hiçbir ipucu vermediğinde (ör. üreticinin kendi iç
# kod adını döndürdüğü durumlar — gerçek bir örnek: bir FortiGate
# `sysDescr` olarak yalnızca dahili "PSL_HQ_FGT" gibi bir kurum-içi
# adlandırma döndürebilir, "fortigate"/"firewall" kelimesi hiç
# geçmeyebilir). Kelime SINIRI (`\b`) ile aranır — "software" gibi bir
# kelimenin içinde YANLIŞLIKLA "fw" alt dizesini yakalamamak için.
_PROFILE_NAME_DEVICE_TYPE_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bfw\b", re.IGNORECASE), "firewall"),
    (re.compile(r"\bfirewall\b", re.IGNORECASE), "firewall"),
    (re.compile(r"\bswitch\b", re.IGNORECASE), "switch"),
    (re.compile(r"\brouter\b", re.IGNORECASE), "router"),
]


def _guess_device_type_from_sys_descr(sys_descr: str | None, profile_name: str | None = None) -> str:
    if sys_descr:
        text = sys_descr.lower()
        for keyword, device_type in _SYS_DESCR_DEVICE_TYPE_HINTS:
            if keyword in text:
                return device_type
    if profile_name:
        for pattern, device_type in _PROFILE_NAME_DEVICE_TYPE_HINTS:
            if pattern.search(profile_name):
                return device_type
    return "network_device"


class SNMPProfileNameConflictError(Exception):
    """`name` UNIQUE kısıtını ihlal eden bir create/update denemesi."""


class SNMPProfileNotFoundError(Exception):
    """Verilen `id` ile eşleşen bir profil yok."""


def is_credential_configured(row: dict) -> bool:
    """v2c: `community_ref` gerçekten çözülüyor mu. v3 noAuthNoPriv:
    hiçbir secret gerekmediği için her zaman `True`. v3 authNoPriv/
    authPriv: gerekli tüm ref'ler gerçekten çözülüyor mu. Secret
    DEĞERİNİN kendisi hiçbir zaman bu fonksiyonun dışına sızmaz —
    yalnızca var/yok bilgisi."""
    if row["version"] == "v2c":
        return resolve_secret(row.get("community_ref"), allow_literal_fallback=True) is not None

    auth_protocol = row.get("auth_protocol")
    if not auth_protocol:
        return True  # noAuthNoPriv — gerekli secret yok
    if resolve_secret(row.get("auth_credential_ref")) is None:
        return False
    priv_protocol = row.get("priv_protocol")
    if priv_protocol and resolve_secret(row.get("priv_credential_ref")) is None:
        return False
    return True


def _to_response(row: dict, assigned_asset_count: int = 0) -> SNMPProfileResponse:
    return row_to_response(
        row, secret_configured=is_credential_configured(row), assigned_asset_count=assigned_asset_count
    )


async def _auto_assign_if_ip_matches(
    conn: asyncpg.Connection,
    profile_id: UUID,
    target_host: str,
    *,
    confirmed_system: SystemInfo | None = None,
    profile_name: str | None = None,
) -> None:
    """Profilin `target_host`'u Varlık Envanterindeki bir asset'in
    `ip_address`'iyle TAM eşleşiyorsa, profili o asset'e otomatik atar
    (kullanıcı isteği — "Atanmış Cihazlar: Cihaz yok" durumunu gidermek
    için). Yalnızca TEK, TAM IP eşleşmesi yeterince güvenilir bir sinyal
    olduğu için otomatik yapılır — Agent↔Asset eşleştirmesindeki (Faz 29
    `matching.py`) çoklu-sinyal temkinliliğinden BİLİNÇLİ bir sapma:
    burada kullanıcı zaten `target_host`'u kendi eliyle, tekil bir hedef
    olarak girmiş durumda. Asset'in ZATEN bir profili varsa (bu profil
    ya da başka biri) SESSİZCE ÜZERİNE YAZILMAZ — kullanıcının kendi
    elle yaptığı bir seçim varsa ona dokunulmaz.

    **Eşleşen asset hiç yoksa** (kullanıcı bildirimiyle bulunan gerçek
    bir kör nokta: ICMP/ARP tabanlı Network Discovery, ICMP'yi
    engelleyen bir firewall/switch'i HİÇBİR ZAMAN "asset" olarak
    kaydetmez — SNMP profili "Hazır" ve "Test Connection" başarılı
    görünse bile, arkasında bir `assets` satırı olmadığı için ne
    Monitoring sayfası ne de arka plan poller'ı (`poll_all`, yalnızca
    MEVCUT asset'leri dolaşır) bu cihazı HİÇ görmezdi): `confirmed_system`
    DOLU verilmişse (yalnızca `test_connection`'ın GERÇEKTEN başarılı
    olduğu dal — bkz. çağrı noktası) bu, cihazın GERÇEKTEN var ve
    erişilebilir olduğunun somut kanıtıdır — bu durumda `target_host`
    için YENİ bir asset satırı, SNMP'den gelen GERÇEK verilerle
    (hostname=sysName, device_type=sysDescr'den çıkarım, ASLA port
    taramasıymış gibi uydurulmaz — bkz. `_guess_device_type_from_sys_
    descr`) oluşturulur, sonra profil ona atanır. `confirmed_system`
    verilmemişse (create/update sırasında — canlı bir poll YAPILMADI)
    hiçbir asset UYDURULMAZ, yalnızca mevcut bir eşleşme aranır."""
    asset = await assets_repo.get_asset_by_ip(conn, target_host)
    if asset is None:
        if confirmed_system is None:
            return
        evidence = [f"SNMP profili '{target_host}' hedefine GERÇEK bir bağlantı ile doğrulandı"]
        if confirmed_system.sys_descr:
            evidence.append(f"sysDescr: {confirmed_system.sys_descr}")
        asset = await assets_repo.upsert_asset(
            conn,
            ip_address=target_host,
            hostname=confirmed_system.sys_name,
            mac_address=None,
            vendor=None,
            device_type=_guess_device_type_from_sys_descr(confirmed_system.sys_descr, profile_name),
            confidence="medium",
            status="up",
            open_ports=[],
            evidence=evidence,
            last_seen=datetime.now(timezone.utc),
        )
    existing = await asset_profiles_repo.get_profile_for_asset(conn, asset["id"])
    if existing is not None:
        return
    await asset_profiles_repo.assign_profile_to_asset(conn, asset_id=asset["id"], profile_id=profile_id)


async def create_profile(conn: asyncpg.Connection, request: SNMPProfileWriteRequest) -> SNMPProfileResponse:
    try:
        row = await profiles_repo.insert_profile(conn, **request.model_dump())
    except asyncpg.UniqueViolationError as exc:
        raise SNMPProfileNameConflictError(f"'{request.name}' adında bir profil zaten var") from exc
    await _auto_assign_if_ip_matches(conn, row["id"], request.target_host)
    count = await asset_profiles_repo.count_assets_for_profile(conn, row["id"])
    return _to_response(row, count)


async def replace_profile(
    conn: asyncpg.Connection, profile_id: UUID, request: SNMPProfileWriteRequest
) -> SNMPProfileResponse:
    try:
        row = await profiles_repo.update_profile(conn, profile_id=profile_id, **request.model_dump())
    except asyncpg.UniqueViolationError as exc:
        raise SNMPProfileNameConflictError(f"'{request.name}' adında bir profil zaten var") from exc
    if row is None:
        raise SNMPProfileNotFoundError(f"Profil bulunamadı: {profile_id}")
    await _auto_assign_if_ip_matches(conn, profile_id, request.target_host)
    count = await asset_profiles_repo.count_assets_for_profile(conn, profile_id)
    return _to_response(row, count)


async def get_profile(conn: asyncpg.Connection, profile_id: UUID) -> SNMPProfileResponse | None:
    row = await profiles_repo.get_profile_by_id(conn, profile_id)
    if row is None:
        return None
    count = await asset_profiles_repo.count_assets_for_profile(conn, profile_id)
    return _to_response(row, count)


async def list_profiles(conn: asyncpg.Connection) -> list[SNMPProfileResponse]:
    rows = await profiles_repo.list_profiles(conn)
    counts = await asset_profiles_repo.count_assets_by_profile(conn)
    return [_to_response(row, counts.get(row["id"], 0)) for row in rows]


class SNMPProfileHasAssignmentsError(Exception):
    """Profil bir veya daha fazla asset'e atanmışken silinmeye
    çalışıldı — CASCADE ile sessizce silinmez, önce ilişkiler kaldırılmalı."""


async def delete_profile(conn: asyncpg.Connection, profile_id: UUID) -> bool:
    assigned_count = await asset_profiles_repo.count_assets_for_profile(conn, profile_id)
    if assigned_count > 0:
        raise SNMPProfileHasAssignmentsError(
            f"Bu profil {assigned_count} asset'e atanmış — önce atamaları kaldırın."
        )
    return await profiles_repo.delete_profile(conn, profile_id)


SNMPTestStatus = Literal[
    "connected", "timeout", "authentication_failed", "unreachable", "not_configured", "error"
]


class SNMPTestConnectionResult(BaseModel):
    status: SNMPTestStatus
    message: str
    sys_name: str | None = None
    sys_descr: str | None = None
    sys_object_id: str | None = None
    sys_uptime_ticks: int | None = None


_POLL_STATUS_TO_TEST_STATUS: dict[str, SNMPTestStatus] = {
    "success": "connected",
    "partial": "connected",
    "timeout": "timeout",
    "unreachable": "unreachable",
    "authentication_failed": "authentication_failed",
    "not_configured": "not_configured",
}


async def test_connection(conn: asyncpg.Connection, profile_id: UUID) -> SNMPTestConnectionResult:
    """Bu profilin `target_host`'una GERÇEK bir SNMP poll dener —
    yalnızca kullanıcının bu profili AÇIKÇA kaydederken kendisinin
    verdiği bir hedefe karşı, kullanıcı bu butona tıkladığında (otomatik
    tarama/probe DEĞİL, bkz. CLAUDE.md ve Faz 29 talimatı §16). Profil
    kaydedilmemişse önce kaydedilmelidir (secret'ın kalıcı olmayan bir
    request'te taşınmasını gerektiren bir "kaydetmeden test et" akışı
    KASITLI olarak eklenmedi — bkz. `docs/decisions.md` §10.3)."""
    row = await profiles_repo.get_profile_by_id(conn, profile_id)
    if row is None:
        raise SNMPProfileNotFoundError(f"Profil bulunamadı: {profile_id}")

    if not row["enabled"]:
        return SNMPTestConnectionResult(status="not_configured", message="Profil devre dışı.")
    if not is_credential_configured(row):
        return SNMPTestConnectionResult(
            status="not_configured", message="Credential .env üzerinden çözülemedi."
        )

    domain_profile = row_to_domain_profile(row, row["id"])
    if domain_profile is None:
        return SNMPTestConnectionResult(status="error", message="Profil yapılandırması geçersiz.")
    try:
        result = await SNMPClient().poll_asset(domain_profile, row["target_host"], row["id"])
    except SNMPError as exc:
        return SNMPTestConnectionResult(
            status="error", message=f"Beklenmeyen bir hata oluştu ({exc.__class__.__name__})."
        )

    test_status = _POLL_STATUS_TO_TEST_STATUS.get(result.status, "error")
    if test_status == "connected":
        # Gerçekten bağlanıldığı doğrulandı — kullanıcı isteği: bu,
        # "kaydet" ile aynı otomatik atama sinyalini tetikler (bkz.
        # `_auto_assign_if_ip_matches`). `result.system` de birlikte
        # geçilir — eşleşen bir asset YOKSA, bu GERÇEK poll sonucundan
        # (uydurma değil) yeni bir asset oluşturulabilsin diye.
        await _auto_assign_if_ip_matches(
            conn, profile_id, row["target_host"], confirmed_system=result.system, profile_name=row["name"]
        )
    message = result.error if result.error else "Bağlantı başarılı."
    system = result.system
    return SNMPTestConnectionResult(
        status=test_status,
        message=message,
        sys_name=system.sys_name if system else None,
        sys_descr=system.sys_descr if system else None,
        sys_object_id=system.sys_object_id if system else None,
        sys_uptime_ticks=system.sys_uptime_ticks if system else None,
    )
