"""SNMP Profile Configuration Center — servis (orkestrasyon) katmanı
(Faz 29). Route'lar ile `app/db/snmp_profiles.py` arasında; secret
çözümleme durumunu hesaplar, gerçek "Test Connection" akışını mevcut
`SNMPClient`'ı (değiştirilmeden) kullanarak yürütür."""

from typing import Literal
from uuid import UUID

import asyncpg
from pydantic import BaseModel

from app.db import asset_snmp_profiles as asset_profiles_repo
from app.db import snmp_profiles as profiles_repo
from app.snmp.client import SNMPClient
from app.snmp.exceptions import SNMPError
from app.snmp.profile_config import (
    SNMPProfileResponse,
    SNMPProfileWriteRequest,
    row_to_domain_profile,
    row_to_response,
)
from app.snmp.secrets import resolve_secret


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
        return resolve_secret(row.get("community_ref")) is not None

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


async def create_profile(conn: asyncpg.Connection, request: SNMPProfileWriteRequest) -> SNMPProfileResponse:
    try:
        row = await profiles_repo.insert_profile(conn, **request.model_dump())
    except asyncpg.UniqueViolationError as exc:
        raise SNMPProfileNameConflictError(f"'{request.name}' adında bir profil zaten var") from exc
    return _to_response(row)  # yeni profilin henüz atanmış asset'i olamaz


async def replace_profile(
    conn: asyncpg.Connection, profile_id: UUID, request: SNMPProfileWriteRequest
) -> SNMPProfileResponse:
    try:
        row = await profiles_repo.update_profile(conn, profile_id=profile_id, **request.model_dump())
    except asyncpg.UniqueViolationError as exc:
        raise SNMPProfileNameConflictError(f"'{request.name}' adında bir profil zaten var") from exc
    if row is None:
        raise SNMPProfileNotFoundError(f"Profil bulunamadı: {profile_id}")
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
